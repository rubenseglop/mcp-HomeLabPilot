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
        if url.endswith("/api/states/sensor.temperature"):
            return FakeResponse({"entity_id": "sensor.temperature", "state": "21.5"})
        if "/api/history/period/" in url:
            return FakeResponse([[{"entity_id": "sensor.temperature", "state": "20.0"}]])
        if url.endswith("/library/sections/1/recentlyAdded"):
            return FakeResponse([{"ratingKey": "101", "title": "Alien"}])
        if url.endswith("/external-api/v1/videos/abcdefghijk"):
            return FakeResponse({"id": "abcdefghijk", "title": "Test video", "status": "downloaded"})
        if url.endswith("/external-api/v1/videos"):
            return FakeResponse({"items": [{"id": "abcdefghijk", "title": "Test video"}]})
        if url.endswith("/api/v1/books/search"):
            return FakeResponse({"total": 1, "items": [{"id": 7, "title": "Dune"}]})
        if url.endswith("/api/v1/books/7"):
            return FakeResponse({"id": 7, "title": "Dune", "formats": ["epub", "pdf"]})
        if url.endswith("/api/v1/statistics/format-distribution"):
            return FakeResponse({"epub": 10, "pdf": 3, "audiobook": 2})
        if url.endswith("/Items"):
            return FakeResponse({"Items": [{"Id": "movie-1", "Name": "Alien"}]})
        if url.endswith("/api/v1/search"):
            return FakeResponse({"results": [{"id": 1, "title": "Alien"}]})
        if url.endswith("/api/search/metadata"):
            return FakeResponse({"assets": [{"id": "asset-1", "originalFileName": "alien.jpg"}]})
        if url.endswith("/api/roms/42"):
            return FakeResponse({"id": 42, "name": "Sonic"})
        if url.endswith("/api/roms"):
            return FakeResponse([{"id": 42, "name": "Sonic"}])
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
    monkeypatch.setenv("HOMEASSISTANT_URL", "http://homeassistant:8123")
    monkeypatch.setenv("HOMEASSISTANT_TOKEN", "homeassistant-read-token")
    monkeypatch.setenv("ROMM_URL", "http://romm:8080")
    monkeypatch.setenv("ROMM_API_TOKEN", "romm-read-token")
    monkeypatch.setenv("PLEX_URL", "http://plex:32400")
    monkeypatch.setenv("PLEX_TOKEN", "plex-read-token")
    monkeypatch.setenv("JELLYFIN_URL", "http://jellyfin:8096")
    monkeypatch.setenv("JELLYFIN_API_KEY", "jellyfin-read-key")
    monkeypatch.setenv("SEERR_URL", "http://seerr:5055")
    monkeypatch.setenv("SEERR_API_KEY", "seerr-read-key")
    monkeypatch.setenv("IMMICH_URL", "http://immich:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "immich-read-key")
    monkeypatch.setenv("BOOKORBIT_URL", "http://bookorbit:8080")
    monkeypatch.setenv("BOOKORBIT_API_KEY", "bookorbit-read-key")
    monkeypatch.setenv("YOUTARR_URL", "http://youtarr:3000")
    monkeypatch.setenv("YOUTARR_API_KEY", "youtarr-read-key")
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



def test_homeassistant_entity_state_accepts_domain_dot_object_id(registered):
    result = asyncio.run(registered["homeassistant_get_state"]("sensor.temperature"))
    assert result == {"entity_id": "sensor.temperature", "state": "21.5"}
    call = FakeAsyncClient.calls[-1]
    assert call["method"] == "GET"
    assert call["url"] == "http://homeassistant:8123/api/states/sensor.temperature"
    assert call["headers"]["Authorization"] == "Bearer homeassistant-read-token"


def test_homeassistant_entity_state_rejects_invalid_entity_id(registered):
    with pytest.raises(ValueError, match="domain.entity_id"):
        asyncio.run(registered["homeassistant_get_state"]("sensor/temperature"))


def test_homeassistant_history_accepts_timezone_aware_timestamps(registered):
    result = asyncio.run(registered["homeassistant_get_history"](
        "sensor.temperature",
        "2026-11-23T00:00:00+01:00",
        "2026-11-23T12:00:00+01:00",
    ))
    assert result == [[{"entity_id": "sensor.temperature", "state": "20.0"}]]
    call = FakeAsyncClient.calls[-1]
    assert call["method"] == "GET"
    assert call["url"].startswith("http://homeassistant:8123/api/history/period/")
    assert call["params"]["filter_entity_id"] == "sensor.temperature"
    assert call["params"]["end_time"] == "2026-11-23T12:00:00+01:00"


def test_homeassistant_history_rejects_timezone_naive_timestamps(registered):
    with pytest.raises(ValueError, match="include a timezone"):
        asyncio.run(registered["homeassistant_get_history"](
            "sensor.temperature", "2026-11-23T00:00:00"
        ))



def test_romm_search_uses_bounded_query_and_bearer_token(registered):
    result = asyncio.run(registered["romm_search_roms"]("Sonic", limit=15, offset=5))
    assert result == [{"id": 42, "name": "Sonic"}]
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://romm:8080/api/roms"
    assert call["params"] == {"search_term": "Sonic", "limit": 15, "offset": 5}
    assert call["headers"]["Authorization"] == "Bearer romm-read-token"


def test_romm_get_rom_returns_game_details(registered):
    result = asyncio.run(registered["romm_get_rom"](42))
    assert result == {"id": 42, "name": "Sonic"}
    assert FakeAsyncClient.calls[-1]["url"] == "http://romm:8080/api/roms/42"


def test_romm_search_rejects_short_terms(registered):
    with pytest.raises(ValueError, match="search_term"):
        asyncio.run(registered["romm_search_roms"]("S"))



def test_plex_dashboard_can_read_recent_items_from_selected_library(registered):
    from homelabpilot import integrations

    monkeypatch_calls = FakeAsyncClient.calls
    result = asyncio.run(integrations_status(registered).dashboard_read(
        "plex", "recent_section", section_id=1, limit=10
    ))
    assert result == [{"ratingKey": "101", "title": "Alien"}]
    call = monkeypatch_calls[-1]
    assert call["url"] == "http://plex:32400/library/sections/1/recentlyAdded"
    assert call["params"]["X-Plex-Container-Size"] == 10
    assert call["params"]["X-Plex-Token"] == "plex-read-token"


def integrations_status(registered):
    # The dashboard reader is attached to the MCP registration's status checker.
    from homelabpilot import integrations
    mcp = FakeMCP()
    return integrations.register_integration_tools(
        mcp=mcp,
        require_permission=lambda _permission: None,
        make_preview_token=lambda snapshot: "signed",
        safe_path=lambda path: path,
        base_url=lambda env: __import__("os").environ[env].rstrip("/"),
        decode_response=lambda response: response.json(),
        audit=lambda *args, **kwargs: None,
        timeout=5,
    )


def test_jellyfin_dashboard_search_uses_existing_read_tool(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("jellyfin", "search", search_term="Alien", limit=12))
    assert result == {"Items": [{"Id": "movie-1", "Name": "Alien"}]}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://jellyfin:8096/Items"
    assert call["params"] == {"searchTerm": "Alien", "Limit": 12, "Recursive": "true"}
    assert call["headers"]["X-Emby-Token"] == "jellyfin-read-key"


def test_seerr_dashboard_search_uses_existing_read_tool(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("seerr", "search", search_term="Alien"))
    assert result == {"results": [{"id": 1, "title": "Alien"}]}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://seerr:5055/api/v1/search"
    assert call["params"] == {"query": "Alien"}
    assert call["headers"]["X-Api-Key"] == "seerr-read-key"


def test_immich_dashboard_search_uses_existing_read_tool(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("immich", "search", search_term="Alien", page=2, size=10))
    assert result == {"assets": [{"id": "asset-1", "originalFileName": "alien.jpg"}]}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://immich:2283/api/search/metadata"
    assert call["json"] == {"query": "Alien", "page": 2, "size": 10}
    assert call["headers"]["X-Api-Key"] == "immich-read-key"



def test_bookorbit_dashboard_search_and_detail_use_existing_read_tools(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("bookorbit", "search", query="Dune", limit=5))
    assert result == {"total": 1, "items": [{"id": 7, "title": "Dune"}]}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://bookorbit:8080/api/v1/books/search"
    assert call["params"] == {"q": "Dune", "limit": 5}
    assert call["headers"]["X-Api-Key"] == "bookorbit-read-key"

    detail = asyncio.run(status.dashboard_read("bookorbit", "book", book_id=7))
    assert detail == {"id": 7, "title": "Dune", "formats": ["epub", "pdf"]}
    assert FakeAsyncClient.calls[-1]["url"] == "http://bookorbit:8080/api/v1/books/7"


def test_bookorbit_dashboard_exposes_format_distribution(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("bookorbit", "format_distribution"))
    assert result == {"epub": 10, "pdf": 3, "audiobook": 2}
    assert FakeAsyncClient.calls[-1]["url"] == "http://bookorbit:8080/api/v1/statistics/format-distribution"



def test_youtarr_dashboard_video_list_supports_search(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read(
        "youtarr", "videos", page_size=15, search="Home Assistant", status="downloaded"
    ))
    assert result == {"items": [{"id": "abcdefghijk", "title": "Test video"}]}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://youtarr:3000/external-api/v1/videos"
    assert call["params"]["pageSize"] == 15
    assert call["params"]["search"] == "Home Assistant"
    assert call["params"]["status"] == "downloaded"
    assert call["headers"]["X-Api-Key"] == "youtarr-read-key"


def test_youtarr_dashboard_video_detail_validates_youtube_id(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("youtarr", "video", youtube_id="abcdefghijk"))
    assert result == {"id": "abcdefghijk", "title": "Test video", "status": "downloaded"}
    assert FakeAsyncClient.calls[-1]["url"] == "http://youtarr:3000/external-api/v1/videos/abcdefghijk"
    with pytest.raises(ValueError, match="11-character"):
        asyncio.run(status.dashboard_read("youtarr", "video", youtube_id="invalid"))
