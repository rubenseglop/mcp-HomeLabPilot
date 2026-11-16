"""Tests for the built-in StackARR browser dashboard."""
import asyncio
import json

from stackarr.web import StackARRWebMiddleware


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

    return StackARRWebMiddleware(fallback, "test-secret-token", status)


def test_dashboard_is_served():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b"StackARR" in body


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
        body=json.dumps({"password": "test-secret-token"}).encode(),
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

    app = StackARRWebMiddleware(fallback, "test-secret-token", status, api)
    start, _ = call_asgi(app, "/web-api/library", headers=[(b"cookie", b"stackarr_session=test-secret-token")])
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

    app = StackARRWebMiddleware(fallback, "test-secret-token", status, api)
    start, _ = call_asgi(app, "/web-api/torrents")
    assert start["status"] == 401



def test_dashboard_settings_includes_prowlarr():
    start, body = call_asgi(make_app(), "/")
    assert start["status"] == 200
    assert b'<option value="prowlarr">Prowlarr</option>' in body
    assert b"prowlarrResources" in body
