"""Tests for the Questarr and Frigate read-only integrations."""

import asyncio
import json

import pytest

from homelabpilot.integrations import HTTP_INTEGRATIONS, register_integration_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


class FakeResponse:
    status_code = 200

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
        if url.endswith("/api/integration/ping"):
            return FakeResponse({"service": "questarr", "version": "1.0", "scope": "read"})
        if url.endswith("/api/integration/library"):
            return FakeResponse({"count": 3, "games": [{"title": "A"}, {"title": "B"}, {"title": "C"}]})
        if url.endswith("/api/stats"):
            return FakeResponse({"cameras": {"front": {"camera_fps": 5}}})
        if url.endswith("/api/events"):
            return FakeResponse([{"id": "event-1"}])
        if url.endswith("/api/review"):
            return FakeResponse([{"id": "review-1"}])
        if url.endswith("/api/review/summary"):
            return FakeResponse({"last24Hours": {"total_alert": 2}})
        if url.endswith("/library/sections"):
            return FakeResponse([{"id": 1, "title": "Movies"}])
        raise AssertionError(f"Unexpected endpoint: {url}")


@pytest.fixture
def registered(monkeypatch):
    from homelabpilot import integrations

    monkeypatch.setenv("QUESTARR_URL", "http://questarr:5000")
    monkeypatch.setenv("QUESTARR_API_KEY", "questarr-read-key")
    monkeypatch.setenv("FRIGATE_URL", "http://frigate:8971")
    monkeypatch.setenv("FRIGATE_API_TOKEN", "frigate-viewer-token")
    FakeAsyncClient.calls = []
    monkeypatch.setattr(integrations.httpx, "AsyncClient", FakeAsyncClient)

    mcp = FakeMCP()
    register_integration_tools(
        mcp=mcp,
        require_permission=lambda _permission: None,
        make_preview_token=lambda snapshot: "signed",
        safe_path=lambda path: path,
        base_url=lambda env: __import__("os").environ[env].rstrip("/"),
        decode_response=lambda response: response.json(),
        audit=lambda *args, **kwargs: None,
        timeout=5,
    )
    return mcp.tools


def test_questarr_and_frigate_are_declared_integrations():
    assert HTTP_INTEGRATIONS["questarr"] == (
        "QUESTARR_URL", "QUESTARR_API_KEY", "x-api-key", "/api/integration/ping"
    )
    assert HTTP_INTEGRATIONS["frigate"] == (
        "FRIGATE_URL", "FRIGATE_API_TOKEN", "bearer", "/api/stats"
    )


def test_questarr_library_uses_read_scoped_key_and_preserves_total(registered):
    result = asyncio.run(registered["questarr_get_library"](limit=2))
    assert result["count"] == 3
    assert result["returned"] == 2
    assert [game["title"] for game in result["games"]] == ["A", "B"]
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://questarr:5000/api/integration/library"
    assert call["headers"]["X-Api-Key"] == "questarr-read-key"
    assert call["params"]["includeHidden"] == "false"


def test_frigate_events_use_bearer_token_and_bounded_query(registered):
    result = asyncio.run(registered["frigate_list_events"](
        limit=25, offset=10, camera="front", label="person"
    ))
    assert result == [{"id": "event-1"}]
    call = FakeAsyncClient.calls[-1]
    assert call["headers"]["Authorization"] == "Bearer frigate-viewer-token"
    assert call["params"]["limit"] == 25
    assert call["params"]["offset"] == 10
    assert call["params"]["include_thumbnails"] == 0


def test_generic_reads_cannot_escape_questarr_or_frigate_allowlists(registered):
    with pytest.raises(PermissionError, match="Questarr"):
        asyncio.run(registered["integration_api_request"](
            "questarr", "GET", "/api/auth/me"
        ))
    with pytest.raises(PermissionError, match="Frigate"):
        asyncio.run(registered["integration_api_request"](
            "frigate", "GET", "/api/config/save"
        ))


@pytest.mark.parametrize("limit", [0, 201])
def test_frigate_event_limit_is_bounded(registered, limit):
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(registered["frigate_list_events"](limit=limit))


def test_dashboard_read_exposes_only_registered_read_operations(monkeypatch):
    from homelabpilot import integrations

    monkeypatch.setenv("PLEX_URL", "http://plex:32400")
    monkeypatch.setenv("PLEX_TOKEN", "plex-token")
    FakeAsyncClient.calls = []
    monkeypatch.setattr(integrations.httpx, "AsyncClient", FakeAsyncClient)
    mcp = FakeMCP()
    status_checks = register_integration_tools(
        mcp=mcp,
        require_permission=lambda _permission: None,
        make_preview_token=lambda snapshot: "signed",
        safe_path=lambda path: path,
        base_url=lambda env: __import__("os").environ[env].rstrip("/"),
        decode_response=lambda response: response.json(),
        audit=lambda *args, **kwargs: None,
        timeout=5,
    )

    result = asyncio.run(status_checks.dashboard_read("plex", "libraries"))
    assert result == [{"id": 1, "title": "Movies"}]
    with pytest.raises(ValueError, match="Unsupported dashboard read operation"):
        asyncio.run(status_checks.dashboard_read("plex", "delete_library"))
