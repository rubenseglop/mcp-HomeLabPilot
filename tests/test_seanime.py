"""Tests for Seanime read-only inspection and guarded settings changes."""

import asyncio
import json

import pytest

from homelabpilot import seanime


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
        self.text = json.dumps(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    calls = []
    settings = {
        "library": {
            "autoUpdateProgress": True,
            "enableManga": False,
            "libraryPath": "/media/anime",
        },
        "torrent": {"qbittorrentPassword": "do-not-return"},
        "nakama": {"hostPassword": "secret"},
    }

    def __init__(self, *args, **kwargs):
        self.headers = kwargs.get("headers", {})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def request(self, method, url, json=None):
        self.calls.append({
            "method": method, "url": url, "json": json, "headers": self.headers,
        })
        if url.endswith("/api/v1/settings") and method == "GET":
            return FakeResponse({"data": self.settings})
        if url.endswith("/api/v1/settings/path") and method == "PATCH":
            path = json["path"].split(".")
            current = self.settings
            for part in path[:-1]:
                current = current[part]
            current[path[-1]] = json["value"]
            return FakeResponse({"data": {"ok": True}})
        raise AssertionError(f"Unexpected Seanime request: {method} {url}")


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setenv("SEANIME_URL", "http://seanime:4321")
    monkeypatch.setenv("SEANIME_PASSWORD", "test-password")
    FakeAsyncClient.calls = []
    FakeAsyncClient.settings = {
        "library": {
            "autoUpdateProgress": True,
            "enableManga": False,
            "libraryPath": "/media/anime",
        },
        "torrent": {"qbittorrentPassword": "do-not-return"},
        "nakama": {"hostPassword": "secret"},
    }
    monkeypatch.setattr(seanime.httpx, "AsyncClient", FakeAsyncClient)
    permissions = []
    snapshots = []

    def make_token(snapshot):
        snapshots.append(snapshot)
        return "signed-preview"

    mcp = FakeMCP()
    seanime.register_seanime_tools(
        mcp, timeout=5, audit=lambda *args: None,
        require_permission=permissions.append, make_preview_token=make_token,
    )
    return mcp.tools, permissions, snapshots


def test_settings_read_redacts_secrets_and_uses_seanime_token(registered):
    tools, _, _ = registered
    result = asyncio.run(tools["seanime_get_settings"]())
    assert result["library"]["autoUpdateProgress"] is True
    assert result["torrent"]["qbittorrentPassword"] == "[REDACTED]"
    assert result["nakama"]["hostPassword"] == "[REDACTED]"
    call = FakeAsyncClient.calls[-1]
    assert call["method"] == "GET"
    assert call["headers"]["X-Seanime-Token"]


def test_setting_preview_is_admin_only_and_signed(registered):
    tools, permissions, snapshots = registered
    result = asyncio.run(tools["seanime_preview_update_setting"](
        "library.enableManga", True
    ))
    assert permissions == ["admin"]
    assert result["current_value"] is False
    assert result["new_value"] is True
    assert result["typed_confirmation"] == "CONFIRM SEANIME SETTING library.enableManga = true"
    assert snapshots[-1]["operation"] == "update-setting"


def test_setting_confirm_requires_exact_preview_and_confirmation(registered):
    tools, permissions, _ = registered
    result = asyncio.run(tools["seanime_confirm_update_setting"](
        "library.enableManga", True, "signed-preview",
        "CONFIRM SEANIME SETTING library.enableManga = true",
    ))
    assert result["changed"] is True
    assert FakeAsyncClient.calls[-1]["method"] == "PATCH"
    assert FakeAsyncClient.calls[-1]["json"] == {
        "path": "library.enableManga", "value": True,
    }
    assert permissions == ["admin"]


@pytest.mark.parametrize("token,phrase", [
    ("wrong-token", "CONFIRM SEANIME SETTING library.enableManga = true"),
    ("signed-preview", "wrong phrase"),
])
def test_setting_confirm_rejects_stale_or_inexact_confirmation(registered, token, phrase):
    tools, _, _ = registered
    with pytest.raises(PermissionError):
        asyncio.run(tools["seanime_confirm_update_setting"](
            "library.enableManga", True, token, phrase
        ))
    assert not any(call["method"] == "PATCH" for call in FakeAsyncClient.calls)


@pytest.mark.parametrize("path,value", [
    ("library.libraryPath", True),
    ("torrent.qbittorrentPassword", True),
    ("library.enableManga", "yes"),
])
def test_setting_preview_rejects_unsafe_paths_and_wrong_types(registered, path, value):
    tools, _, _ = registered
    with pytest.raises(ValueError):
        asyncio.run(tools["seanime_preview_update_setting"](path, value))
    assert not FakeAsyncClient.calls


def test_setting_confirm_rechecks_current_value_before_patch(registered):
    tools, _, _ = registered
    asyncio.run(tools["seanime_preview_update_setting"]("library.enableManga", True))
    FakeAsyncClient.settings["library"]["enableManga"] = True
    with pytest.raises(PermissionError, match="stale"):
        asyncio.run(tools["seanime_confirm_update_setting"](
            "library.enableManga", True, "signed-preview",
            "CONFIRM SEANIME SETTING library.enableManga = true",
        ))
    assert not any(call["method"] == "PATCH" for call in FakeAsyncClient.calls)
