"""Tdarr MCP read and guarded-operation tests."""

import asyncio
import json
import os

import pytest

from homelabpilot import integrations


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.content = json.dumps(payload).encode()
        self.text = self.content.decode()

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def request(self, method, url, params=None, json=None, headers=None, auth=None):
        self.calls.append({
            "method": method, "url": url, "params": params,
            "json": json, "headers": headers,
        })
        if url.endswith("/api/v2/status"):
            return FakeResponse({"version": "2.40.01", "status": "ok"})
        if url.endswith("/api/v2/get-nodes"):
            return FakeResponse({"nodeList": [{"nodeName": "worker-1"}]})
        if url.endswith("/api/v2/search-db"):
            return FakeResponse({"results": [{"file": "/media/a.mkv"}]})
        if url.endswith("/api/v2/client/jobs"):
            return FakeResponse({"jobs": [{"_id": "job-1"}]})
        if url.endswith("/api/v2/job-reports/job-1"):
            return FakeResponse({"_id": "job-1", "log": "completed"})
        if url.endswith("/api/v2/bulk-update-files"):
            return FakeResponse({"updated": 1})
        if url.endswith("/api/v2/rescan-file"):
            return FakeResponse({"queued": True})
        raise AssertionError(f"Unexpected Tdarr request: {method} {url}")


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setenv("TDARR_URL", "http://tdarr:8265")
    monkeypatch.setenv("TDARR_API_KEY", "tdarr-read-key")
    FakeAsyncClient.calls = []
    monkeypatch.setattr(integrations.httpx, "AsyncClient", FakeAsyncClient)
    permissions = []
    mcp = FakeMCP()
    status = integrations.register_integration_tools(
        mcp=mcp,
        require_permission=permissions.append,
        make_preview_token=lambda snapshot: "signed:" + snapshot["operation"],
        safe_path=lambda path: path,
        base_url=lambda env: os.environ[env].rstrip("/"),
        decode_response=lambda response: response.json(),
        audit=lambda *args, **kwargs: None,
        timeout=5,
    )
    return mcp.tools, permissions, status


def test_tdarr_all_read_tools_use_fixed_read_endpoints(registered):
    tools, _, _ = registered
    assert asyncio.run(tools["tdarr_get_status"]())["status"] == "ok"
    assert asyncio.run(tools["tdarr_get_nodes"]())["nodeList"][0]["nodeName"] == "worker-1"
    assert asyncio.run(tools["tdarr_search_files"]("movie", 1, 20))["results"]
    assert asyncio.run(tools["tdarr_list_job_reports"](0, 10, "/media"))["jobs"]
    assert asyncio.run(tools["tdarr_get_job_report"]("job-1"))["log"] == "completed"
    assert [call["method"] for call in FakeAsyncClient.calls] == [
        "GET", "GET", "POST", "POST", "GET",
    ]
    assert all(call["headers"]["X-Api-Key"] == "tdarr-read-key" for call in FakeAsyncClient.calls)
    assert FakeAsyncClient.calls[2]["url"].endswith("/api/v2/search-db")
    assert FakeAsyncClient.calls[3]["url"].endswith("/api/v2/client/jobs")


@pytest.mark.parametrize("kwargs", [
    {"search_term": "x" * 301},
    {"greater_than_gb": -1},
    {"greater_than_gb": 20, "less_than_gb": 10},
])
def test_tdarr_search_rejects_invalid_bounds_before_request(registered, kwargs):
    tools, _, _ = registered
    with pytest.raises(ValueError):
        asyncio.run(tools["tdarr_search_files"](**kwargs))
    assert FakeAsyncClient.calls == []


@pytest.mark.parametrize("start,page_size", [(-1, 10), (0, 0), (0, 101)])
def test_tdarr_job_report_pagination_is_bounded(registered, start, page_size):
    tools, _, _ = registered
    with pytest.raises(ValueError):
        asyncio.run(tools["tdarr_list_job_reports"](start, page_size))
    assert FakeAsyncClient.calls == []


def test_tdarr_requeue_requires_permission_and_signed_exact_confirmation(registered):
    tools, permissions, _ = registered
    preview = asyncio.run(tools["tdarr_preview_requeue_files"](["file-1", "file-1"]))
    assert preview["files_to_requeue"] == ["file-1"]
    assert permissions == ["operations"]
    with pytest.raises(PermissionError):
        asyncio.run(tools["tdarr_confirm_requeue_files"](
            ["file-1"], "stale", preview["typed_confirmation"]
        ))
    assert FakeAsyncClient.calls == []
    result = asyncio.run(tools["tdarr_confirm_requeue_files"](
        ["file-1"], preview["preview_token"], preview["typed_confirmation"]
    ))
    assert result == {"updated": 1}
    assert FakeAsyncClient.calls[-1]["url"].endswith("/api/v2/bulk-update-files")


def test_tdarr_rescan_requires_preview_and_exact_confirmation(registered):
    tools, permissions, _ = registered
    preview = asyncio.run(tools["tdarr_preview_rescan_file"]("file-1", "library-1"))
    assert permissions == ["operations"]
    with pytest.raises(PermissionError):
        asyncio.run(tools["tdarr_confirm_rescan_file"](
            "file-1", "library-1", preview["preview_token"], "not exact"
        ))
    assert FakeAsyncClient.calls == []
    result = asyncio.run(tools["tdarr_confirm_rescan_file"](
        "file-1", "library-1", preview["preview_token"], preview["typed_confirmation"]
    ))
    assert result == {"queued": True}
    assert FakeAsyncClient.calls[-1]["json"] == {
        "data": {"_id": "file-1", "DB": "library-1"}
    }


def test_tdarr_bulk_actions_reject_unbounded_or_empty_file_lists(registered):
    tools, _, _ = registered
    for ids in ([], [f"file-{i}" for i in range(51)]):
        with pytest.raises(ValueError):
            asyncio.run(tools["tdarr_preview_requeue_files"](ids))
    assert FakeAsyncClient.calls == []
