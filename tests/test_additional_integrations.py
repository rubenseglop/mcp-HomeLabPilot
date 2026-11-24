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

    async def post(self, url, json=None, headers=None, auth=None):
        return await self.request("POST", url, json=json, headers=headers, auth=auth)

    async def request(self, method, url, params=None, json=None, headers=None, auth=None):
        self.calls.append({
            "method": method, "url": url, "params": params,
            "json": json, "headers": headers, "auth": auth,
        })
        if url.endswith("/api/system"):
            return FakeResponse({"message": "OK", "data": {
                "version": "5.3.5", "state": "RUNNING", "busy": False,
                "queuedMainTasks": 0, "runningTasks": [],
                "imageDownloadsRunning": False, "poolRunning": True,
            }})
        if url.endswith("/v1"):
            command = (json or {}).get("cmd")
            if command == "sessions.list":
                return FakeResponse({"status": "ok", "sessions": ["homelabpilot-test"]})
            if command == "request.get":
                return FakeResponse({"status": "ok", "solution": {
                    "url": (json or {}).get("url"),
                    "response": "x" * 21000,
                }})
        if url.endswith("/transmission/rpc"):
            method = (json or {}).get("method")
            if method == "torrent-get":
                return FakeResponse({"arguments": {"torrents": [{
                    "id": 7, "name": "Linux ISO", "status": 4, "percentDone": 1.0,
                    "ratio": 1.5, "peersConnected": 12, "files": [], "trackers": [],
                }]}})
            return FakeResponse({"arguments": {}})
        if url.endswith("/api/integration/ping"):
            return FakeResponse({"service": "questarr", "version": "1.0", "scope": "read"})
        if url.endswith("/api/integration/library"):
            return FakeResponse({"count": 3, "games": [{"title": "A"}, {"title": "B"}, {"title": "C"}]})
        if url.endswith("/api/stats"):
            return FakeResponse({"cameras": {"front": {"camera_fps": 5}}})
        if url.endswith("/dns_records"):
            return FakeResponse({"success": True, "result": [{"id": "a" * 32, "type": "A", "name": "media.example.com", "content": "192.0.2.10"}], "result_info": {"page": 1, "per_page": 100, "total_count": 1}})
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
        if url.endswith("/api/tasks/Collection%20Handler"):
            return FakeResponse({"name": "Collection Handler", "running": False, "lastRun": "2026-11-23T20:00:00Z"})
        if url.endswith("/api/v2/public/servers"):
            return FakeResponse({"servers": [{"id": "server-1", "name": "Plex", "healthy": True}]})
        if url.endswith("/api/v2/public/libraries"):
            return FakeResponse({"libraries": [{"name": "Movies", "items": 120}]})
        if url.endswith("/api/v2/public/top-media"):
            return FakeResponse({"items": [{"title": "Alien", "plays": 12}], "nextCursor": None})
        if url.endswith("/api/v2/public/recently-added"):
            return FakeResponse({"items": [{"id": "media-1", "title": "Alien"}], "nextCursor": None})
        if url.endswith("/api/v2/public/history"):
            return FakeResponse({"items": [{"id": "play-1", "title": "Alien", "user": "guest"}], "nextCursor": None})
        if url.endswith("/api/events/timeline"):
            return FakeResponse({"hours": 168, "series": [{"hour": "2026-11-23T12:00:00Z", "count": 3}]})
        if url.endswith("/api/strikes/recent"):
            return FakeResponse([{"id": 9, "reason": "low seeders"}])
        if url.endswith("/api/strikes"):
            return FakeResponse({"items": [{"id": 8, "type": "warning"}], "total": 1})
        if url.endswith("/api/jobs"):
            return FakeResponse([{"name": "cleanup", "state": "idle"}])
        if url.endswith("/api/manualevents/stats"):
            return FakeResponse({"unresolved": 2, "critical": 1})
        if url.endswith("/api/v1/missing-items"):
            return FakeResponse({"items": [{"id": 12, "title": "Dune"}], "total": 1})
        if url.endswith("/api/v1/missing-items/stats"):
            return FakeResponse({"pending": 2, "available": 5})
        if url.endswith("/api/v1/dashboard/activity"):
            return FakeResponse({"days": 7, "topMedia": [{"title": "Dune"}]})
        if url.endswith("/api/queue/status"):
            return FakeResponse({"paused": False, "rateLimited": False, "pending": 4})
        if url.endswith("/api/queue/list"):
            return FakeResponse({"items": [{"id": 17, "title": "Tidal track", "status": "downloading"}], "total": 1})
        if url.endswith("/api/history/list"):
            return FakeResponse({"items": [{"id": 12, "title": "Completed track"}]})
        if url.endswith("/api/sync/list"):
            return FakeResponse({"items": [{"id": 3, "name": "Road trip playlist"}]})
        if url.endswith("/external-api/v1/videos/abcdefghijk"):
            return FakeResponse({"id": "abcdefghijk", "title": "Test video", "status": "downloaded"})
        if url.endswith("/external-api/v1/requests/42"):
            return FakeResponse({"id": 42, "status": "completed", "youtubeId": "abcdefghijk"})
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
    monkeypatch.setenv("TIDARR_URL", "http://tidarr:8080")
    monkeypatch.setenv("TIDARR_API_KEY", "tidarr-read-key")
    monkeypatch.setenv("AGREGARR_URL", "http://agregarr:7171")
    monkeypatch.setenv("AGREGARR_API_KEY", "agregarr-read-key")
    monkeypatch.setenv("CLOUDFLARE_API_URL", "https://api.cloudflare.com/client/v4")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-read-token")
    monkeypatch.setenv("CLEANUPARR_URL", "http://cleanuparr:11011")
    monkeypatch.setenv("CLEANUPARR_API_KEY", "cleanuparr-read-token")
    monkeypatch.setenv("TRACEARR_URL", "http://tracearr:3000")
    monkeypatch.setenv("TRACEARR_API_KEY", "tracearr-read-token")
    monkeypatch.setenv("MAINTAINERR_URL", "http://maintainerr:6246")
    monkeypatch.setenv("TRANSMISSION_URL", "http://transmission:9091/transmission/rpc")
    monkeypatch.setenv("FLARESOLVERR_URL", "http://flaresolverr:8191")
    monkeypatch.setenv("TINYMEDIAMANAGER_URL", "http://tinymediamanager:7878")
    monkeypatch.setenv("TINYMEDIAMANAGER_API_KEY", "tmm-read-key")
    monkeypatch.setenv("TRANSMISSION_USERNAME", "transmission-user")
    monkeypatch.setenv("TRANSMISSION_PASSWORD", "transmission-password")
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


def test_youtarr_dashboard_request_detail_validates_positive_id(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("youtarr", "request_detail", request_id=42))
    assert result == {"id": 42, "status": "completed", "youtubeId": "abcdefghijk"}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://youtarr:3000/external-api/v1/requests/42"
    assert call["headers"]["X-Api-Key"] == "youtarr-read-key"
    with pytest.raises(ValueError, match="positive"):
        asyncio.run(status.dashboard_read("youtarr", "request_detail", request_id=0))



def test_tidarr_dashboard_exposes_queue_pause_and_rate_limit_status(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("tidarr", "queue_status"))
    assert result == {"paused": False, "rateLimited": False, "pending": 4}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://tidarr:8080/api/queue/status"
    assert call["headers"]["X-Api-Key"] == "tidarr-read-key"


def test_tidarr_dashboard_lists_download_queue_with_bounded_pagination(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("tidarr", "queue", offset=10, limit=25))
    assert result == {"items": [{"id": 17, "title": "Tidal track", "status": "downloading"}], "total": 1}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://tidarr:8080/api/queue/list"
    assert call["params"] == {"offset": 10, "limit": 25}
    assert call["headers"]["X-Api-Key"] == "tidarr-read-key"
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(status.dashboard_read("tidarr", "queue", limit=500))


def test_tidarr_dashboard_exposes_download_history_and_sync_playlists(registered):
    status = integrations_status(registered)
    history = asyncio.run(status.dashboard_read("tidarr", "history"))
    assert history == {"items": [{"id": 12, "title": "Completed track"}]}
    history_call = FakeAsyncClient.calls[-1]
    assert history_call["url"] == "http://tidarr:8080/api/history/list"
    assert history_call["headers"]["X-Api-Key"] == "tidarr-read-key"

    sync_list = asyncio.run(status.dashboard_read("tidarr", "sync_list"))
    assert sync_list == {"items": [{"id": 3, "name": "Road trip playlist"}]}
    sync_call = FakeAsyncClient.calls[-1]
    assert sync_call["url"] == "http://tidarr:8080/api/sync/list"
    assert sync_call["headers"]["X-Api-Key"] == "tidarr-read-key"



def test_agregarr_dashboard_lists_missing_items_with_bounded_pagination(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read(
        "agregarr", "missing_items", limit=20, offset=10, status="pending", media_type="movie"
    ))
    assert result == {"items": [{"id": 12, "title": "Dune"}], "total": 1}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://agregarr:7171/api/v1/missing-items"
    assert call["params"] == {
        "limit": 20, "offset": 10, "status": "pending", "mediaType": "movie"
    }
    assert call["headers"]["X-Api-Key"] == "agregarr-read-key"


def test_agregarr_dashboard_reads_missing_stats_and_activity(registered):
    status = integrations_status(registered)
    stats = asyncio.run(status.dashboard_read("agregarr", "missing_item_stats"))
    assert stats == {"pending": 2, "available": 5}
    activity = asyncio.run(status.dashboard_read("agregarr", "activity", days=7, limit=10))
    assert activity == {"days": 7, "topMedia": [{"title": "Dune"}]}
    assert FakeAsyncClient.calls[-1]["params"] == {"days": 7, "limit": 10}



def test_cloudflare_dashboard_lists_dns_records_for_selected_zone(registered):
    status = integrations_status(registered)
    zone_id = "a" * 32
    result = asyncio.run(status.dashboard_read(
        "cloudflare", "dns_records", zone_id=zone_id,
        record_type="A", name="media.example.com", page=1, per_page=50,
    ))
    assert result["success"] is True
    assert result["result"][0]["name"] == "media.example.com"
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    assert call["params"] == {
        "page": 1, "per_page": 50, "type": "A", "name": "media.example.com"
    }
    assert call["headers"]["Authorization"] == "Bearer cloudflare-read-token"


def test_cloudflare_dashboard_dns_records_rejects_invalid_zone_id(registered):
    status = integrations_status(registered)
    with pytest.raises(ValueError, match="32-character Cloudflare zone ID"):
        asyncio.run(status.dashboard_read("cloudflare", "dns_records", zone_id="invalid"))



def test_cleanuparr_dashboard_exposes_event_timeline_and_strikes(registered):
    status = integrations_status(registered)
    timeline = asyncio.run(status.dashboard_read("cleanuparr", "event_timeline", hours=72))
    assert timeline["hours"] == 168
    assert FakeAsyncClient.calls[-1]["url"] == "http://cleanuparr:11011/api/events/timeline"
    assert FakeAsyncClient.calls[-1]["params"] == {"hours": 72}

    recent = asyncio.run(status.dashboard_read("cleanuparr", "recent_strikes", count=5))
    assert recent == [{"id": 9, "reason": "low seeders"}]
    assert FakeAsyncClient.calls[-1]["params"] == {"count": 5}

    strikes = asyncio.run(status.dashboard_read(
        "cleanuparr", "strikes", page=2, page_size=10, search="Ubuntu", strike_type="warning"
    ))
    assert strikes == {"items": [{"id": 8, "type": "warning"}], "total": 1}
    assert FakeAsyncClient.calls[-1]["params"] == {
        "page": 2, "pageSize": 10, "search": "Ubuntu", "type": "warning"
    }


def test_cleanuparr_dashboard_exposes_jobs_and_manual_event_statistics(registered):
    status = integrations_status(registered)
    jobs = asyncio.run(status.dashboard_read("cleanuparr", "jobs"))
    assert jobs == [{"name": "cleanup", "state": "idle"}]
    assert FakeAsyncClient.calls[-1]["url"] == "http://cleanuparr:11011/api/jobs"

    stats = asyncio.run(status.dashboard_read("cleanuparr", "manual_event_stats"))
    assert stats == {"unresolved": 2, "critical": 1}
    assert FakeAsyncClient.calls[-1]["url"] == "http://cleanuparr:11011/api/manualevents/stats"



def test_tracearr_dashboard_lists_servers_and_recent_media(registered):
    status = integrations_status(registered)
    servers = asyncio.run(status.dashboard_read("tracearr", "servers"))
    assert servers == {"servers": [{"id": "server-1", "name": "Plex", "healthy": True}]}
    assert FakeAsyncClient.calls[-1]["url"] == "http://tracearr:3000/api/v2/public/servers"

    recent = asyncio.run(status.dashboard_read("tracearr", "recently_added", page_size=15))
    assert recent == {"items": [{"id": "media-1", "title": "Alien"}], "nextCursor": None}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://tracearr:3000/api/v2/public/recently-added"
    assert call["params"] == {"pageSize": 15}
    assert call["headers"]["Authorization"] == "Bearer tracearr-read-token"


def test_tracearr_dashboard_reads_watch_history_with_bounded_page_size(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("tracearr", "watch_history", page_size=20))
    assert result == {"items": [{"id": "play-1", "title": "Alien", "user": "guest"}], "nextCursor": None}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://tracearr:3000/api/v2/public/history"
    assert call["params"] == {"pageSize": 20}



def test_maintainerr_dashboard_reads_allowlisted_scheduled_task_status(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read(
        "maintainerr", "task_status", task_name="Collection Handler"
    ))
    assert result == {
        "name": "Collection Handler", "running": False,
        "lastRun": "2026-11-23T20:00:00Z",
    }
    assert FakeAsyncClient.calls[-1]["url"] == (
        "http://maintainerr:6246/api/tasks/Collection%20Handler"
    )
    with pytest.raises(ValueError, match="task_name"):
        asyncio.run(status.dashboard_read("maintainerr", "task_status", task_name="arbitrary"))



def test_tracearr_dashboard_reads_library_statistics_and_top_media(registered):
    status = integrations_status(registered)
    libraries = asyncio.run(status.dashboard_read("tracearr", "libraries"))
    assert libraries == {"libraries": [{"name": "Movies", "items": 120}]}
    assert FakeAsyncClient.calls[-1]["url"] == "http://tracearr:3000/api/v2/public/libraries"

    top = asyncio.run(status.dashboard_read(
        "tracearr", "top_media", media_type="movie", days=30,
        sort="plays", page_size=15,
    ))
    assert top == {"items": [{"title": "Alien", "plays": 12}], "nextCursor": None}
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://tracearr:3000/api/v2/public/top-media"
    assert call["params"] == {
        "media_type": "movie", "days": 30, "sort": "plays", "pageSize": 15
    }


def test_transmission_dashboard_reads_extended_details_for_one_torrent(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read(
        "transmission", "torrent_details",
        ids=[7],
        fields=[
            "id", "name", "status", "percentDone", "totalSize", "downloadDir",
            "addedDate", "doneDate", "rateDownload", "rateUpload", "eta",
            "uploadedEver", "downloadedEver", "ratio", "peersConnected",
            "peersGettingFromUs", "peersSendingToUs", "error", "errorString",
            "files", "fileStats", "trackers",
        ],
    ))
    torrent = result["arguments"]["torrents"][0]
    assert torrent["name"] == "Linux ISO"
    assert torrent["ratio"] == 1.5
    call = FakeAsyncClient.calls[-1]
    assert call["method"] == "POST"
    assert call["url"] == "http://transmission:9091/transmission/rpc"
    assert call["json"]["method"] == "torrent-get"
    assert call["json"]["arguments"]["ids"] == [7]
    assert "trackers" in call["json"]["arguments"]["fields"]
    assert call["auth"] == ("transmission-user", "transmission-password")


def test_flaresolverr_dashboard_fetches_public_page_and_truncates_response(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read(
        "flaresolverr", "request_get",
        url="https://example.org/catalog", max_timeout=45000,
    ))
    assert result["status"] == "ok"
    assert result["solution"]["url"] == "https://example.org/catalog"
    assert result["solution"]["response"].endswith("[truncated by HomeLabPilot]")
    call = FakeAsyncClient.calls[-1]
    assert call["url"] == "http://flaresolverr:8191/v1"
    assert call["json"] == {
        "cmd": "request.get", "url": "https://example.org/catalog", "maxTimeout": 45000,
    }


def test_flaresolverr_request_get_rejects_private_targets(registered):
    status = integrations_status(registered)
    for target in ("http://127.0.0.1/admin", "http://192.168.1.10/", "http://printer.local/"):
        with pytest.raises(ValueError):
            asyncio.run(status.dashboard_read("flaresolverr", "request_get", url=target))
    assert not [call for call in FakeAsyncClient.calls if call["url"].endswith("/v1")]


def test_tinymediamanager_dashboard_exposes_task_queue_from_status(registered):
    status = integrations_status(registered)
    result = asyncio.run(status.dashboard_read("tinymediamanager", "tasks"))
    assert result["data"]["queuedMainTasks"] == 0
