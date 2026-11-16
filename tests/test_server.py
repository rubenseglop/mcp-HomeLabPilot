"""Small unit tests for StackARR path validation."""
import pytest

from stackarr.server import _safe_path


@pytest.mark.parametrize("path", ["/api/v3/movie", "/api/v2/torrents/info"])
def test_safe_path_accepts_api_paths(path):
    assert _safe_path(path) == path


@pytest.mark.parametrize(
    "path",
    ["", "api/v3/movie", "//evil.example/path", "https://evil.example", "/\\evil", "/api/v3/../admin"],
)
def test_safe_path_rejects_non_api_paths(path):
    with pytest.raises(ValueError):
        _safe_path(path)



def test_web_catalog_search_dispatches_to_shared_arr_lookup(monkeypatch):
    import asyncio
    import stackarr.server as server

    async def fake_search(service, term):
        return [{"service": service, "term": term}]

    monkeypatch.setattr(server, "arr_search_catalog", fake_search)
    result = asyncio.run(server._web_api_request(
        "/web-api/catalog", "GET", {"service": ["radarr"], "term": ["Dune"]}, {}
    ))
    assert result == [{"service": "radarr", "term": "Dune"}]


def test_web_add_dispatches_to_movie_or_series(monkeypatch):
    import asyncio
    import stackarr.server as server

    calls = []

    async def fake_movie(*args, **kwargs):
        calls.append(("radarr", args, kwargs))
        return {"id": 42}

    async def fake_series(*args, **kwargs):
        calls.append(("sonarr", args, kwargs))
        return {"id": 84}

    monkeypatch.setattr(server, "arr_add_movie", fake_movie)
    monkeypatch.setattr(server, "arr_add_series", fake_series)
    movie = asyncio.run(server._web_api_request(
        "/web-api/catalog/add", "POST", {},
        {"service": "radarr", "tmdb_id": 123, "root_folder_path": "/movies", "quality_profile_id": 4},
    ))
    series = asyncio.run(server._web_api_request(
        "/web-api/catalog/add", "POST", {},
        {"service": "sonarr", "tvdb_id": 456, "root_folder_path": "/series", "quality_profile_id": 5},
    ))
    assert movie == {"id": 42}
    assert series == {"id": 84}
    assert calls[0][0] == "radarr" and calls[0][1][0] == 123
    assert calls[1][0] == "sonarr" and calls[1][1][0] == 456


def test_web_add_rejects_unknown_service():
    import asyncio
    import stackarr.server as server

    with pytest.raises(ValueError, match="service must be radarr or sonarr"):
        asyncio.run(server._web_api_request("/web-api/catalog/add", "POST", {}, {"service": "prowlarr"}))



@pytest.mark.parametrize(
    ("status_code", "body"),
    [(204, ""), (200, "Ok.")],
)
def test_qbittorrent_login_accepts_success_responses(status_code, body):
    from types import SimpleNamespace
    from stackarr.server import _check_qbittorrent_login

    response = SimpleNamespace(
        status_code=status_code,
        text=body,
        raise_for_status=lambda: None,
    )
    _check_qbittorrent_login(response)


def test_qbittorrent_login_rejects_unexpected_response():
    from types import SimpleNamespace
    from stackarr.server import _check_qbittorrent_login

    response = SimpleNamespace(
        status_code=200,
        text="Fails.",
        raise_for_status=lambda: None,
    )
    with pytest.raises(RuntimeError, match="rejected"):
        _check_qbittorrent_login(response)


def test_arr_configuration_update_rejects_unknown_resource():
    import asyncio
    import stackarr.server as server

    with pytest.raises(ValueError, match="resource must be one of"):
        asyncio.run(server.arr_update_configuration("radarr", "system", 1, {"id": 1}))


def test_qbittorrent_preferences_reject_sensitive_or_unknown_keys(monkeypatch):
    import asyncio
    import stackarr.server as server

    async def fake_request(method, path, params=None, data=None):
        return {"ok": True}

    monkeypatch.setattr(server, "qbittorrent_api_request", fake_request)
    with pytest.raises(ValueError, match="Unsupported qBittorrent preferences"):
        asyncio.run(server.qbittorrent_update_preferences({"web_ui_password": "secret"}))



def test_arr_configuration_redacts_secret_fields_recursively():
    from stackarr.server import _redact_sensitive_config

    original = {
        "id": 7,
        "name": "Indexer",
        "fields": [
            {"name": "baseUrl", "value": "https://indexer.example"},
            {"name": "apiKey", "value": "secret-api-key"},
            {"name": "password", "value": "secret-password"},
        ],
        "nested": {"accessToken": "secret-token", "enabled": True},
    }
    safe = _redact_sensitive_config(original)
    assert safe["fields"][0]["value"] == "https://indexer.example"
    assert safe["fields"][1] == {"name": "apiKey"}
    assert safe["fields"][2] == {"name": "password"}
    assert safe["nested"] == {"enabled": True}
    assert "secret-api-key" not in repr(safe)
    assert "secret-password" not in repr(safe)
    assert "secret-token" not in repr(safe)


def test_arr_update_configuration_restores_redacted_secrets(monkeypatch):
    import asyncio
    import stackarr.server as server

    calls = []
    current = {
        "id": 7,
        "name": "Indexer",
        "fields": [
            {"name": "apiKey", "value": "keep-this-key"},
            {"name": "baseUrl", "value": "https://old.example"},
        ],
        "password": "keep-this-password",
    }

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, body))
        if method == "GET":
            return current
        return body

    monkeypatch.setattr(server, "_arr_request", fake_request)
    submitted = server._redact_sensitive_config(current)
    submitted["name"] = "Updated indexer"
    submitted["fields"][1]["value"] = "https://new.example"
    result = asyncio.run(server.arr_update_configuration("radarr", "indexer", 7, submitted))

    assert result["fields"][0]["value"] == "keep-this-key"
    assert result["password"] == "keep-this-password"
    assert result["fields"][1]["value"] == "https://new.example"
    assert calls[0][1:3] == ("GET", "/api/v3/indexer/7")
    assert calls[1][1:3] == ("PUT", "/api/v3/indexer/7")




def test_prowlarr_configuration_uses_v1_endpoints(monkeypatch):
    import asyncio
    import stackarr.server as server

    calls = []

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, body))
        if method == "GET":
            return [{"id": 9, "name": "Indexer", "apiKey": "hidden"}]
        return body

    monkeypatch.setattr(server, "_arr_request", fake_request)
    result = asyncio.run(server.arr_get_configuration("prowlarr", "indexer"))
    assert result == [{"id": 9, "name": "Indexer"}]

    updated = asyncio.run(server.arr_update_configuration(
        "prowlarr", "indexer", 9, {"id": 9, "name": "Updated"}
    ))
    assert updated["apiKey"] == "hidden"
    assert calls[0][0:3] == ("prowlarr", "GET", "/api/v1/indexer")
    assert calls[1][0:3] == ("prowlarr", "GET", "/api/v1/indexer/9")
    assert calls[2][0:3] == ("prowlarr", "PUT", "/api/v1/indexer/9")


def test_prowlarr_configuration_rejects_unsupported_resource():
    import asyncio
    import stackarr.server as server

    with pytest.raises(ValueError, match="resource for prowlarr"):
        asyncio.run(server.arr_get_configuration("prowlarr", "qualityprofile"))
