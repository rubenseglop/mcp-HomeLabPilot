"""Tests for the built-in HomeLabPilot browser dashboard."""
import asyncio
import json

import pytest

from homelabpilot.web import DASHBOARD, HomeLabPilotWebMiddleware


def call_asgi(app, path, method="GET", headers=None, body=b""):
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "server": ("test", 80),
        "client": ("test", 1234),
    }
    asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    payload = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start, payload


def make_app():
    async def status():
        return {"services": {"radarr": {"ok": True, "version": "test"}}}

    async def fallback(scope, receive, send):
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return HomeLabPilotWebMiddleware(fallback, "test-secret-token", status, web_username="testuser", web_password="test-password")


def test_dashboard_is_served():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"HomeLabPilot" in body


def test_dashboard_api_requires_login():
    start, _ = call_asgi(make_app(), "/web-api/status")
    assert start["status"] == 401


def test_login_sets_cookie_and_cookie_authorizes_dashboard_api():
    app = make_app()
    start, _ = call_asgi(
        app,
        "/web-login",
        method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    assert start["status"] == 200
    cookie = next(value for name, value in start["headers"] if name == b"set-cookie")
    assert b"HttpOnly" in cookie

    start, body = call_asgi(
        app,
        "/web-api/status",
        headers=[(b"cookie", cookie.split(b";", 1)[0])],
    )
    assert start["status"] == 200
    assert b'"radarr"' in body



def test_authenticated_web_api_calls_shared_backend():
    calls = []

    async def api(path, method, query, payload):
        calls.append((path, method, query, payload))
        return {"items": ["example"]}

    async def status():
        return {"services": {}}

    async def fallback(scope, receive, send):
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = HomeLabPilotWebMiddleware(fallback, "test-secret-token", status, api, web_username="testuser", web_password="test-password")
    login, _ = call_asgi(app, "/web-login", method="POST", headers=[(b"content-type", b"application/json")], body=json.dumps({"username": "testuser", "password": "test-password"}).encode())
    cookie = next(value.split(b";", 1)[0] for name, value in login["headers"] if name == b"set-cookie")
    start, _ = call_asgi(app, "/web-api/library", headers=[(b"cookie", cookie)])
    assert start["status"] == 200
    assert calls[0][0] == "/web-api/library"
    assert calls[0][1] == "GET"


def test_web_api_requires_session():
    async def api(path, method, query, payload):
        return {}

    async def status():
        return {"services": {}}

    async def fallback(scope, receive, send):
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = HomeLabPilotWebMiddleware(fallback, "test-secret-token", status, api)
    start, _ = call_asgi(app, "/web-api/torrents")
    assert start["status"] == 401



def test_dashboard_exposes_advanced_api_explorer_and_bazarr():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b'data-view="api-explorer"' in body
    assert b'<option value="bazarr">Bazarr</option>' in body
    assert b'/web-api/api' in body


def test_web_api_advanced_api_dispatches_to_shared_permission_checked_bridge(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_arr_api_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, params, body))
        return {"ok": True}

    monkeypatch.setattr(server, "arr_api_request", fake_arr_api_request)
    result = asyncio.run(server._web_api_request(
        "/web-api/api", "POST", {},
        {"service": "bazarr", "method": "PUT", "path": "/api/providers/1",
         "params": {"enabled": True}, "body": {"name": "Example"}},
    ))
    assert result == {"ok": True}
    assert calls == [("bazarr", "PUT", "/api/providers/1",
                      {"enabled": True}, {"name": "Example"})]


def test_web_api_advanced_api_rejects_unknown_service():
    import asyncio
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="service must be radarr"):
        asyncio.run(server._web_api_request(
            "/web-api/api", "POST", {},
            {"service": "docker", "method": "GET", "path": "/containers"},
        ))


def test_web_api_advanced_api_rejects_non_object_params():
    import asyncio
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="params must be a JSON object"):
        asyncio.run(server._web_api_request(
            "/web-api/api", "POST", {},
            {"service": "radarr", "method": "GET", "path": "/api/v3/movie",
             "params": []},
        ))


def test_dashboard_settings_includes_prowlarr():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b'<option value="prowlarr">Prowlarr</option>' in body
    assert b"prowlarrResources" in body


def test_dashboard_login_rejects_wrong_username_or_password():
    app = make_app()
    start, _ = call_asgi(
        app, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "wrong", "password": "test-password"}).encode(),
    )
    assert start["status"] == 401


def test_dashboard_session_is_random_and_not_the_mcp_token():
    app = make_app()
    start, _ = call_asgi(
        app, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    cookie = next(value for name, value in start["headers"] if name == b"set-cookie")
    assert b"test-secret-token" not in cookie
    assert b"HttpOnly" in cookie


def test_dashboard_library_view_has_monitor_and_quality_profile_controls():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"data-library-monitored" in body
    assert b"data-library-profile" in body
    assert b"/web-api/library/update" in body


def test_dashboard_library_has_release_search_and_grab_controls():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"data-library-releases" in body
    assert b"data-grab-release" in body
    assert b"/web-api/releases/grab" in body


def test_dashboard_session_survives_middleware_restart():
    first = make_app()
    login, _ = call_asgi(
        first, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    cookie = next(value.split(b";", 1)[0] for name, value in login["headers"] if name == b"set-cookie")

    # A new middleware instance represents a container/process restart.
    restarted = make_app()
    start, body = call_asgi(restarted, "/web-api/status", headers=[(b"cookie", cookie)])
    assert start["status"] == 200
    assert b'"radarr"' in body


def test_dashboard_session_rejects_tampered_cookie():
    app = make_app()
    login, _ = call_asgi(
        app, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    cookie = next(value.split(b";", 1)[0] for name, value in login["headers"] if name == b"set-cookie")
    name, value = cookie.split(b"=", 1)
    tampered = value[:-1] + (b"A" if value[-1:] != b"A" else b"B")
    start, _ = call_asgi(app, "/web-api/status", headers=[(b"cookie", name + b"=" + tampered)])
    assert start["status"] == 401


def test_dashboard_cookie_is_persistent_for_thirty_days():
    app = make_app()
    login, _ = call_asgi(
        app, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    cookie = next(value for name, value in login["headers"] if name == b"set-cookie")
    assert b"Max-Age=2592000" in cookie



def test_library_table_passes_rows_as_an_array():
    library_view = DASHBOARD.split("const rows=(library||[]).map(x=>{", 1)[1].split(
        "html='<h3>'+ (view==='movies'?'Movies':'Series')", 1
    )[0]
    assert "}).join('')" not in library_view
    assert "});" in library_view


def test_downloads_view_exposes_category_and_safe_remove_controls():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"data-torrent-set-category" in body
    assert b"data-torrent-delete" in body
    assert b"delete_files:false" in body
    assert body.count("HomeLabPilot · Web dashboard and MCP endpoint in one application".encode()) == 1


def test_dashboard_surfaces_backend_error_details_and_uses_live_scryer_schema():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"data.error||data.detail||data.message" in body
    assert b"query StackStatus { scryerVersion }" not in body
    assert b"Write a query using an operation shown in the schema above." in body


def test_authenticated_web_api_rejects_cross_origin_post():
    app = make_app()
    login, _ = call_asgi(
        app, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    cookie = next(value.split(b";", 1)[0] for name, value in login["headers"] if name == b"set-cookie")
    start, body = call_asgi(
        app, "/web-api/torrents/control", method="POST",
        headers=[
            (b"cookie", cookie), (b"host", b"homelabpilot.local"),
            (b"origin", b"https://attacker.example"),
            (b"content-type", b"application/json"),
        ],
        body=b'{"action":"pause","hashes":"abc"}',
    )
    assert start["status"] == 403
    assert b"Cross-origin" in body


def test_authenticated_web_api_allows_same_origin_post():
    app = make_app()
    login, _ = call_asgi(
        app, "/web-login", method="POST",
        headers=[(b"content-type", b"application/json")],
        body=json.dumps({"username": "testuser", "password": "test-password"}).encode(),
    )
    cookie = next(value.split(b";", 1)[0] for name, value in login["headers"] if name == b"set-cookie")
    start, _ = call_asgi(
        app, "/web-api/torrents/control", method="POST",
        headers=[
            (b"cookie", cookie), (b"host", b"homelabpilot.local"),
            (b"origin", b"https://homelabpilot.local"),
            (b"content-type", b"application/json"),
        ],
        body=b'{}',
    )
    assert start["status"] == 404


def test_settings_dashboard_has_configuration_create_edit_delete_controls():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"/web-api/settings/create" in body
    assert b"/web-api/settings/delete" in body
    assert b"Create configuration record" in body
    assert b"Preview delete" in body
    assert b"/web-api/settings/preview-delete" in body


def test_dashboard_has_persistent_english_spanish_language_switch():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b'data-language="en"' in body and "🇬🇧".encode() in body
    assert b'data-language="es"' in body and "🇪🇸".encode() in body
    assert b"homelabpilot-language" in body
    assert "Películas".encode() in body
    assert b"'Save changes':'Guardar cambios'" in body
    assert b"'Preview delete':'Vista previa del borrado'" in body
    assert b"closest('[data-config-form]')" in body


def test_dashboard_exposes_complete_lidarr_music_workflows():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    for marker in (
        'data-view="artists"', 'data-view="lidarr-queue"',
        'data-view="lidarr-history"', 'data-view="lidarr-missing"',
        'data-view="search-artists"', 'data-artist-albums',
        'data-album-save', 'value="lidarr"', 'metadata_profiles',
        'foreignArtistId',
    ):
        assert marker.encode() in body



def test_dashboard_exposes_codex_chat_workspace():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    for marker in (
        'data-view="agent-chat"',
        "AI Chat · Agents",
        "Claude Code",
        "Gemini",
        "agent-provider",
        "/web-api/agents/status",
        "/web-api/agents/chat",
        "/web-api/agents/job",
        "renderAgentConversation",
        "Read-only mode",
    ):
        assert marker.encode() in body



def test_operation_history_formats_timestamps_in_madrid_local_time():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"function formatOperationDate(value)" in body
    assert b"timeZone:'Europe/Madrid'" in body
    assert b"formatOperationDate(x.occurred_at)" in body
    assert b"Local time" in body
    assert b"Time (UTC)" not in body
