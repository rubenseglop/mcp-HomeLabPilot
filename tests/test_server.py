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
