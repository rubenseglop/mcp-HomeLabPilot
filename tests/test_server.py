"""Small unit tests for HomeLabPilot path validation."""
import pytest

from homelabpilot.server import _safe_path


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
    import homelabpilot.server as server

    async def fake_search(service, term):
        return [{"service": service, "term": term}]

    monkeypatch.setattr(server, "arr_search_catalog", fake_search)
    result = asyncio.run(server._web_api_request(
        "/web-api/catalog", "GET", {"service": ["radarr"], "term": ["Dune"]}, {}
    ))
    assert result == [{"service": "radarr", "term": "Dune"}]


def test_web_add_dispatches_to_movie_or_series(monkeypatch):
    import asyncio
    import homelabpilot.server as server

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
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="service must be radarr, sonarr or lidarr"):
        asyncio.run(server._web_api_request("/web-api/catalog/add", "POST", {}, {"service": "prowlarr"}))



@pytest.mark.parametrize(
    ("status_code", "body"),
    [(204, ""), (200, "Ok.")],
)
def test_qbittorrent_login_accepts_success_responses(status_code, body):
    from types import SimpleNamespace
    from homelabpilot.server import _check_qbittorrent_login

    response = SimpleNamespace(
        status_code=status_code,
        text=body,
        raise_for_status=lambda: None,
    )
    _check_qbittorrent_login(response)


def test_qbittorrent_login_rejects_unexpected_response():
    from types import SimpleNamespace
    from homelabpilot.server import _check_qbittorrent_login

    response = SimpleNamespace(
        status_code=200,
        text="Fails.",
        raise_for_status=lambda: None,
    )
    with pytest.raises(RuntimeError, match="rejected"):
        _check_qbittorrent_login(response)


def test_arr_configuration_update_rejects_unknown_resource(monkeypatch):
    import asyncio
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")

    with pytest.raises(ValueError, match="resource for radarr must be one of"):
        asyncio.run(server.arr_update_configuration("radarr", "system", 1, {"id": 1}))


def test_qbittorrent_preferences_reject_sensitive_or_unknown_keys(monkeypatch):
    import asyncio
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")

    async def fake_request(method, path, params=None, data=None):
        return {"ok": True}

    monkeypatch.setattr(server, "qbittorrent_api_request", fake_request)
    with pytest.raises(ValueError, match="Unsupported qBittorrent preferences"):
        asyncio.run(server.qbittorrent_update_preferences({"web_ui_password": "secret"}))



def test_arr_configuration_redacts_secret_fields_recursively():
    from homelabpilot.server import _redact_sensitive_config

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
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")

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
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")

    calls = []

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, body))
        if method == "GET" and path == "/api/v1/indexer":
            return [{"id": 9, "name": "Indexer"}]
        if method == "GET":
            return {"id": 9, "name": "Indexer", "apiKey": "hidden"}
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
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="resource for prowlarr"):
        asyncio.run(server.arr_get_configuration("prowlarr", "qualityprofile"))


def test_arr_update_library_item_preserves_existing_fields_and_updates_requested_values(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []
    current = {
        "id": 42, "title": "Example", "monitored": True,
        "qualityProfileId": 3, "rootFolderPath": "/media/movies",
        "images": [{"coverType": "poster", "url": "/poster.jpg"}],
    }

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, body))
        return current if method == "GET" else body

    monkeypatch.setattr(server, "_arr_request", fake_request)
    result = asyncio.run(server.arr_update_library_item(
        "radarr", 42, monitored=False, quality_profile_id=7
    ))

    assert result["monitored"] is False
    assert result["qualityProfileId"] == 7
    assert result["rootFolderPath"] == "/media/movies"
    assert result["images"] == current["images"]
    assert calls[0][0:3] == ("radarr", "GET", "/api/v3/movie/42")
    assert calls[1][0:3] == ("radarr", "PUT", "/api/v3/movie/42")


def test_arr_update_library_item_rejects_empty_update():
    import asyncio
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="At least one"):
        asyncio.run(server.arr_update_library_item("sonarr", 1))


def test_web_library_update_dispatches_only_requested_fields(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_update(service, item_id, monitored=None, quality_profile_id=None, metadata_profile_id=None):
        calls.append((service, item_id, monitored, quality_profile_id, metadata_profile_id))
        return {"id": item_id}

    monkeypatch.setattr(server, "arr_update_library_item", fake_update)
    result = asyncio.run(server._web_api_request(
        "/web-api/library/update", "POST", {},
        {"service": "sonarr", "id": 84, "monitored": True, "quality_profile_id": 5},
    ))

    assert result == {"id": 84}
    assert calls == [("sonarr", 84, True, 5, None)]


def test_web_release_routes_dispatch_search_and_grab(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_search(service, item_id):
        calls.append(("search", service, item_id))
        return [{"guid": "release-guid"}]

    async def fake_grab(service, guid, indexer_id):
        calls.append(("grab", service, guid, indexer_id))
        return {"queued": True}

    monkeypatch.setattr(server, "arr_search_releases", fake_search)
    monkeypatch.setattr(server, "arr_grab_release", fake_grab)
    releases = asyncio.run(server._web_api_request(
        "/web-api/releases", "GET", {"service": ["radarr"], "id": ["42"]}, {}
    ))
    grabbed = asyncio.run(server._web_api_request(
        "/web-api/releases/grab", "POST", {},
        {"service": "radarr", "guid": "release-guid", "indexer_id": 8},
    ))

    assert releases == [{"guid": "release-guid"}]
    assert grabbed == {"queued": True}
    assert calls == [("search", "radarr", 42), ("grab", "radarr", "release-guid", 8)]



@pytest.mark.parametrize(
    ("level", "required", "allowed"),
    [
        ("read", "read", True),
        ("read", "operations", False),
        ("operations", "operations", True),
        ("operations", "admin", False),
        ("admin", "admin", True),
    ],
)
def test_permission_levels_enforce_hierarchy(monkeypatch, level, required, allowed):
    from homelabpilot.server import _require_permission

    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", level)
    if allowed:
        _require_permission(required)
    else:
        with pytest.raises(PermissionError, match="requires"):
            _require_permission(required)


def test_invalid_permission_level_fails_closed(monkeypatch):
    from homelabpilot.server import _require_permission

    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "superuser")
    with pytest.raises(RuntimeError, match="must be read, operations or admin"):
        _require_permission("read")


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/v3/movie", "read"),
        ("POST", "/api/v3/movie", "operations"),
        ("PUT", "/api/v3/series/12", "operations"),
        ("DELETE", "/api/v3/movie/12", "admin"),
        ("PUT", "/api/v3/qualityprofile/2", "admin"),
        ("POST", "/api/v1/indexer", "admin"),
        ("POST", "/api/v3/command", "admin"),
        ("POST", "/api/v3/rootfolder", "admin"),
        ("PUT", "/api/v3/qualitydefinition/1", "admin"),
        ("PUT", "/api/v3/customformat/2", "admin"),
        ("POST", "/api/v1/importlist", "admin"),
        ("PUT", "/api/providers/1", "admin"),
    ],
)
def test_generic_arr_api_permission_classification(method, path, expected):
    from homelabpilot.server import _arr_api_required_permission

    assert _arr_api_required_permission(method, path) == expected


def test_read_permission_blocks_generic_arr_write_before_api_call(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    async def unexpected_request(*args, **kwargs):
        raise AssertionError("API must not be called when permission is denied")

    monkeypatch.setattr(server, "_arr_request", unexpected_request)
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "read")
    with pytest.raises(PermissionError, match="requires 'operations'"):
        asyncio.run(server.arr_api_request("radarr", "POST", "/api/v3/movie", body={"tmdbId": 1}))


def test_operations_permission_blocks_destructive_arr_api_write(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    async def unexpected_request(*args, **kwargs):
        raise AssertionError("API must not be called when permission is denied")

    monkeypatch.setattr(server, "_arr_request", unexpected_request)
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "operations")
    with pytest.raises(PermissionError, match="requires 'admin'"):
        asyncio.run(server.arr_api_request("radarr", "DELETE", "/api/v3/movie/12"))


def test_scryer_mutation_requires_admin(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "operations")
    with pytest.raises(PermissionError, match="requires 'admin'"):
        asyncio.run(server.scryer_graphql("mutation { deleteMovie(id: 1) { id } }"))


def test_expanded_arr_configuration_resources_are_registered():
    from homelabpilot.server import ARR_EDITABLE_RESOURCES_BY_SERVICE

    expected = {
        "qualitydefinition", "customformat", "importlist", "metadata", "tag",
    }
    assert expected.issubset(ARR_EDITABLE_RESOURCES_BY_SERVICE["radarr"])
    assert expected.issubset(ARR_EDITABLE_RESOURCES_BY_SERVICE["sonarr"])
    assert "languageprofile" in ARR_EDITABLE_RESOURCES_BY_SERVICE["sonarr"]
    assert "releaseprofile" in ARR_EDITABLE_RESOURCES_BY_SERVICE["sonarr"]
    assert "languageprofile" not in ARR_EDITABLE_RESOURCES_BY_SERVICE["radarr"]


def test_web_scryer_graphql_dispatches_query_and_variables(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_graphql(query, variables=None, operation_name=None):
        calls.append((query, variables, operation_name))
        return {"data": {"scryerVersion": "test"}}

    monkeypatch.setattr(server, "scryer_graphql", fake_graphql)
    result = asyncio.run(server._web_api_request(
        "/web-api/scryer/graphql", "POST", {},
        {"query": "query { scryerVersion }", "variables": {"verbose": True}},
    ))
    assert result == {"data": {"scryerVersion": "test"}}
    assert calls == [("query { scryerVersion }", {"verbose": True}, None)]


def test_web_scryer_graphql_rejects_invalid_variables():
    import asyncio
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="variables must be a JSON object"):
        asyncio.run(server._web_api_request(
            "/web-api/scryer/graphql", "POST", {},
            {"query": "query { scryerVersion }", "variables": []},
        ))


def test_web_torrent_category_route_dispatches_to_shared_tool(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_set_category(hashes, category):
        calls.append((hashes, category))
        return {"ok": True}

    monkeypatch.setattr(server, "qbittorrent_set_category", fake_set_category)
    result = asyncio.run(server._web_api_request(
        "/web-api/torrents/category", "POST", {},
        {"hashes": "abc123", "category": "series"},
    ))
    assert result == {"ok": True}
    assert calls == [("abc123", "series")]


def test_web_torrent_delete_route_dispatches_to_shared_tool(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_delete(hashes, preview_token, typed_confirmation, delete_files=False):
        calls.append((hashes, preview_token, typed_confirmation, delete_files))
        return {"ok": True}

    monkeypatch.setattr(server, "qbittorrent_delete_torrents", fake_delete)
    result = asyncio.run(server._web_api_request(
        "/web-api/torrents/delete", "POST", {},
        {"hashes": "abc123", "delete_files": False,
         "preview_token": "preview", "typed_confirmation": "DELETE TORRENT"},
    ))
    assert result == {"ok": True}
    assert calls == [("abc123", "preview", "DELETE TORRENT", False)]


def test_web_torrent_delete_rejects_non_boolean_delete_files():
    import asyncio
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="delete_files must be a boolean"):
        asyncio.run(server._web_api_request(
            "/web-api/torrents/delete", "POST", {},
            {"hashes": "abc123", "delete_files": "true"},
        ))


def test_arr_configuration_create_requires_admin_and_redacts_response(monkeypatch):
    import asyncio
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")
    calls = []

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, body))
        return {"id": 12, "name": "Indexer", "apiKey": "secret"}

    monkeypatch.setattr(server, "_arr_request", fake_request)
    result = asyncio.run(server.arr_create_configuration(
        "prowlarr", "indexer", {"id": 0, "name": "Indexer"}
    ))
    assert calls == [("prowlarr", "POST", "/api/v1/indexer", {"id": 0, "name": "Indexer"})]
    assert result == {"id": 12, "name": "Indexer"}


def test_arr_configuration_create_rejects_existing_id(monkeypatch):
    import asyncio
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")
    with pytest.raises(ValueError, match="id omitted or set to 0"):
        asyncio.run(server.arr_create_configuration("radarr", "indexer", {"id": 9}))


def test_arr_configuration_delete_requires_admin_and_uses_allowlisted_resource(monkeypatch):
    import asyncio
    import homelabpilot.server as server
    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "admin")
    monkeypatch.setenv("HOMELABPILOT_PREVIEW_SECRET", "test-preview-secret-with-at-least-32-characters")
    calls = []

    current = {"id": 7, "name": "Indexer", "enable": True}

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path))
        return current if method == "GET" else {"http_status": 200}

    monkeypatch.setattr(server, "_arr_request", fake_request)
    preview = asyncio.run(server.arr_preview_delete_configuration("sonarr", "notification", 7))
    result = asyncio.run(server.arr_delete_configuration(
        "sonarr", "notification", 7, preview["preview_token"], preview["confirmation_text"]
    ))
    assert result == {"http_status": 200}
    assert calls == [
        ("sonarr", "GET", "/api/v3/notification/7"),
        ("sonarr", "GET", "/api/v3/notification/7"),
        ("sonarr", "DELETE", "/api/v3/notification/7"),
    ]


def test_web_configuration_create_and_delete_routes_dispatch(monkeypatch):
    import asyncio
    import homelabpilot.server as server
    calls = []

    async def fake_create(service, resource, item):
        calls.append(("create", service, resource, item))
        return {"id": 5}

    async def fake_delete(service, resource, item_id, preview_token, typed_confirmation):
        calls.append(("delete", service, resource, item_id, preview_token, typed_confirmation))
        return {"ok": True}

    monkeypatch.setattr(server, "arr_create_configuration", fake_create)
    monkeypatch.setattr(server, "arr_delete_configuration", fake_delete)
    created = asyncio.run(server._web_api_request(
        "/web-api/settings/create", "POST", {},
        {"service": "radarr", "resource": "indexer", "item": {"id": 0}},
    ))
    deleted = asyncio.run(server._web_api_request(
        "/web-api/settings/delete", "POST", {},
        {"service": "radarr", "resource": "indexer", "id": 5,
         "preview_token": "preview", "typed_confirmation": "DELETE radarr/indexer/5: Test"},
    ))
    assert created == {"id": 5}
    assert deleted == {"ok": True}
    assert calls == [
        ("create", "radarr", "indexer", {"id": 0}),
        ("delete", "radarr", "indexer", 5, "preview", "DELETE radarr/indexer/5: Test"),
    ]


def test_lidarr_is_registered_with_native_api_v1():
    from homelabpilot.server import ARR_SERVICES, ARR_EDITABLE_RESOURCES_BY_SERVICE

    assert ARR_SERVICES["lidarr"] == ("LIDARR_URL", "LIDARR_API_KEY", "/api/v1")
    assert ARR_EDITABLE_RESOURCES_BY_SERVICE["lidarr"]["qualityprofile"] == "/api/v1/qualityprofile"
    assert ARR_EDITABLE_RESOURCES_BY_SERVICE["lidarr"]["metadataprofile"] == "/api/v1/metadataprofile"


def test_lidarr_artist_library_and_update_preserve_existing_fields(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []
    current = {"id": 12, "artistName": "Example Artist", "monitored": True,
               "qualityProfileId": 2, "metadataProfileId": 3, "rootFolderPath": "/music",
               "images": [{"coverType": "poster"}]}

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, params, body))
        return [current] if method == "GET" and path == "/api/v1/artist" else current if method == "GET" else body

    monkeypatch.setattr(server, "_arr_request", fake_request)
    library = asyncio.run(server.arr_list_library("lidarr"))
    updated = asyncio.run(server.arr_update_library_item(
        "lidarr", 12, monitored=False, quality_profile_id=7, metadata_profile_id=8
    ))

    assert library == [current]
    assert calls[0][0:3] == ("lidarr", "GET", "/api/v1/artist")
    assert calls[1][0:3] == ("lidarr", "GET", "/api/v1/artist/12")
    assert calls[2][0:3] == ("lidarr", "PUT", "/api/v1/artist/12")
    assert updated["monitored"] is False
    assert updated["qualityProfileId"] == 7
    assert updated["metadataProfileId"] == 8
    assert updated["rootFolderPath"] == "/music"
    assert updated["images"] == current["images"]


def test_lidarr_setup_options_include_metadata_profiles(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    async def fake_request(service, method, path, params=None, body=None):
        return [{"path": path}] if "rootfolder" in path else [{"name": path}]

    monkeypatch.setattr(server, "_arr_request", fake_request)
    result = asyncio.run(server.arr_get_setup_options("lidarr"))
    assert result["root_folders"] == [{"path": "/api/v1/rootfolder"}]
    assert result["quality_profiles"] == [{"name": "/api/v1/qualityprofile"}]
    assert result["metadata_profiles"] == [{"name": "/api/v1/metadataprofile"}]


def test_lidarr_add_artist_uses_musicbrainz_id_and_profiles(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "operations")
    calls = []

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, body))
        return {"id": 21}

    monkeypatch.setattr(server, "_arr_request", fake_request)
    result = asyncio.run(server.arr_add_artist(
        "musicbrainz-uuid", "Example Artist", "/music", 4, 6, search_now=True
    ))
    assert result == {"id": 21}
    assert calls[0][0:3] == ("lidarr", "POST", "/api/v1/artist")
    assert calls[0][3]["foreignArtistId"] == "musicbrainz-uuid"
    assert calls[0][3]["artistName"] == "Example Artist"
    assert calls[0][3]["qualityProfileId"] == 4
    assert calls[0][3]["metadataProfileId"] == 6
    assert calls[0][3]["addOptions"]["searchForMissingAlbums"] is True


def test_lidarr_albums_queue_history_and_missing_use_v1_endpoints(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, params, body))
        return {"records": []} if path in {"/api/v1/queue", "/api/v1/history", "/api/v1/wanted/missing"} else []

    monkeypatch.setattr(server, "_arr_request", fake_request)
    asyncio.run(server.lidarr_list_albums(21))
    asyncio.run(server.arr_get_queue("lidarr"))
    asyncio.run(server.lidarr_get_history())
    asyncio.run(server.lidarr_get_missing_albums())

    assert calls[0][2] == "/api/v1/album"
    assert calls[0][3]["artistId"] == 21
    assert calls[1][2] == "/api/v1/queue"
    assert calls[1][3]["includeAlbum"] == "true"
    assert calls[2][2] == "/api/v1/history"
    assert calls[3][2] == "/api/v1/wanted/missing"


def test_lidarr_release_search_and_grab_use_api_v1(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "operations")
    calls = []

    async def fake_request(service, method, path, params=None, body=None):
        calls.append((service, method, path, params, body))
        return [{"guid": "release"}] if method == "GET" else {"queued": True}

    monkeypatch.setattr(server, "_arr_request", fake_request)
    releases = asyncio.run(server.arr_search_releases("lidarr", 88))
    grabbed = asyncio.run(server.arr_grab_release("lidarr", "release-guid", 4))
    assert releases == [{"guid": "release"}]
    assert grabbed == {"queued": True}
    assert calls[0][2:4] == ("/api/v1/release", {"albumId": 88})
    assert calls[1][0:3] == ("lidarr", "POST", "/api/v1/release")


def test_lidarr_web_routes_dispatch_artist_album_history_and_missing(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_add(*args, **kwargs):
        calls.append(("add", args, kwargs))
        return {"id": 5}

    async def fake_albums(artist_id=None):
        calls.append(("albums", artist_id))
        return [{"id": 8}]

    async def fake_update(album_id, monitored):
        calls.append(("update", album_id, monitored))
        return {"id": album_id}

    async def fake_history():
        return {"records": [{"id": 1}]}

    async def fake_missing():
        return {"records": [{"id": 2}]}

    monkeypatch.setattr(server, "arr_add_artist", fake_add)
    monkeypatch.setattr(server, "lidarr_list_albums", fake_albums)
    monkeypatch.setattr(server, "lidarr_update_album", fake_update)
    monkeypatch.setattr(server, "lidarr_get_history", fake_history)
    monkeypatch.setattr(server, "lidarr_get_missing_albums", fake_missing)

    added = asyncio.run(server._web_api_request("/web-api/catalog/add", "POST", {}, {
        "service": "lidarr", "foreign_artist_id": "mbid", "artist_name": "Artist",
        "root_folder_path": "/music", "quality_profile_id": 2, "metadata_profile_id": 3,
    }))
    albums = asyncio.run(server._web_api_request("/web-api/albums", "GET", {"artist_id": ["5"]}, {}))
    updated = asyncio.run(server._web_api_request("/web-api/albums/update", "POST", {}, {"id": 8, "monitored": False}))
    history = asyncio.run(server._web_api_request("/web-api/history", "GET", {"service": ["lidarr"]}, {}))
    missing = asyncio.run(server._web_api_request("/web-api/missing", "GET", {"service": ["lidarr"]}, {}))

    assert added == {"id": 5}
    assert albums == [{"id": 8}]
    assert updated == {"id": 8}
    assert history["records"][0]["id"] == 1
    assert missing["records"][0]["id"] == 2
    assert calls[0][0] == "add"
    assert calls[1] == ("albums", 5)
    assert calls[2] == ("update", 8, False)


def test_lidarr_album_update_preserves_other_fields(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "operations")
    current = {"id": 8, "title": "Album", "monitored": True, "artistId": 3, "profileId": 4}

    async def fake_request(service, method, path, params=None, body=None):
        return current if method == "GET" else body

    monkeypatch.setattr(server, "_arr_request", fake_request)
    updated = asyncio.run(server.lidarr_update_album(8, False))
    assert updated["monitored"] is False
    assert updated["artistId"] == 3
    assert updated["profileId"] == 4

def test_stack_status_marks_missing_services_as_unconfigured(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    for url_env, key_env, _ in server.ARR_SERVICES.values():
        monkeypatch.delenv(url_env, raising=False)
        monkeypatch.delenv(key_env, raising=False)
    for name in (
        "SCRYER_URL", "SCRYER_API_KEY", "QBITTORRENT_URL",
        "QBITTORRENT_USERNAME", "QBITTORRENT_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    async def unexpected_call(*args, **kwargs):
        raise AssertionError("An unconfigured service must not be contacted")

    async def no_integrations():
        return {}

    monkeypatch.setattr(server, "_arr_request", unexpected_call)
    monkeypatch.setattr(server, "scryer_graphql", unexpected_call)
    monkeypatch.setattr(server, "qbittorrent_api_request", unexpected_call)
    monkeypatch.setattr(server, "integration_status", no_integrations)

    result = asyncio.run(server.stack_status())
    for service in (*server.ARR_SERVICES, "scryer", "qbittorrent"):
        assert result["services"][service] == {"configured": False, "ok": False}


def test_stack_status_lists_tools_for_connected_services_only(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    import homelabpilot.server as server

    for service, (url_env, key_env, _prefix) in server.ARR_SERVICES.items():
        enabled = service in {"radarr", "sonarr", "prowlarr"}
        monkeypatch.setenv(url_env, "http://example.invalid" if enabled else "")
        monkeypatch.setenv(key_env, "test-key" if enabled else "")
    monkeypatch.delenv("SCRYER_URL", raising=False)
    monkeypatch.delenv("SCRYER_API_KEY", raising=False)
    monkeypatch.delenv("QBITTORRENT_URL", raising=False)

    async def fake_arr_request(service, method, path, params=None, body=None):
        return {"version": "6.0.0", "appName": "Radarr"}

    async def no_integrations():
        return {}

    monkeypatch.setattr(server, "_arr_request", fake_arr_request)
    monkeypatch.setattr(server, "integration_status", no_integrations)
    monkeypatch.setattr(
        server.mcp._tool_manager,
        "list_tools",
        lambda: [
            SimpleNamespace(name="arr_api_request", description="Read ARR API"),
            SimpleNamespace(name="arr_list_library", description="List movie, series or artist library"),
            SimpleNamespace(name="arr_add_movie", description="Add movie"),
            SimpleNamespace(name="arr_add_series", description="Add series"),
            SimpleNamespace(name="sonarr_get_series", description="List series"),
            SimpleNamespace(name="prowlarr_get_indexers", description="List indexers"),
        ],
    )

    result = asyncio.run(server.stack_status())
    radarr = result["services"]["radarr"]
    assert radarr["ok"] is True
    assert radarr["tool_count"] == 3
    assert [tool["name"] for tool in radarr["tools"]] == [
        "arr_add_movie", "arr_api_request", "arr_list_library"
    ]
    sonarr = result["services"]["sonarr"]
    assert sonarr["ok"] is True
    assert sonarr["tool_count"] == 3
    assert [tool["name"] for tool in sonarr["tools"]] == [
        "arr_add_series", "arr_api_request", "arr_list_library", "sonarr_get_series"
    ]
    prowlarr = result["services"]["prowlarr"]
    assert prowlarr["ok"] is True
    assert prowlarr["tool_count"] == 7
    assert [tool["name"] for tool in prowlarr["tools"]] == [
        "arr_api_request", "arr_create_configuration", "arr_delete_configuration",
        "arr_get_configuration", "arr_preview_delete_configuration",
        "arr_update_configuration", "prowlarr_get_indexers"
    ]

def test_app_config_is_encrypted_and_never_returns_secret(monkeypatch, tmp_path):
    import os
    import homelabpilot.config_store as config_store

    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "app-config.enc")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-mcp-token-that-is-long-enough-123456")
    monkeypatch.setenv("RADARR_URL", "http://radarr:7878")
    monkeypatch.setenv("RADARR_API_KEY", "do-not-return-this-secret")
    monkeypatch.setenv("QBITTORRENT_USERNAME", "private-user")

    config = config_store.get_app_config()["radarr"]["fields"]
    url = next(field for field in config if field["key"] == "RADARR_URL")
    secret = next(field for field in config if field["key"] == "RADARR_API_KEY")
    assert url["value"] == "http://radarr:7878"
    assert secret["value"] == ""
    assert secret["secret_set"] is True
    qbit_user = next(
        field for field in config_store.get_app_config()["qbittorrent"]["fields"]
        if field["key"] == "QBITTORRENT_USERNAME"
    )
    assert qbit_user["value"] == ""
    assert qbit_user["secret_set"] is True

    config_store.save_app_config("radarr", {
        "RADARR_URL": "http://radarr:7879",
        "RADARR_API_KEY": "",
    })
    encrypted = config_store.CONFIG_PATH.read_bytes()
    assert b"do-not-return-this-secret" not in encrypted
    assert os.stat(config_store.CONFIG_PATH).st_mode & 0o777 == 0o600
    assert os.environ["RADARR_URL"] == "http://radarr:7879"
    assert os.environ["RADARR_API_KEY"] == "do-not-return-this-secret"

    monkeypatch.delenv("RADARR_URL")
    monkeypatch.delenv("RADARR_API_KEY")
    config_store.load_saved_config()
    assert os.environ["RADARR_URL"] == "http://radarr:7879"
    assert os.environ["RADARR_API_KEY"] == "do-not-return-this-secret"


def test_app_config_rejects_unknown_fields_and_unsafe_urls(monkeypatch, tmp_path):
    import pytest
    import homelabpilot.config_store as config_store

    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "app-config.enc")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-mcp-token-that-is-long-enough-123456")
    with pytest.raises(ValueError, match="Unsupported configuration field"):
        config_store.save_app_config("radarr", {"UNRELATED_SECRET": "value"})
    with pytest.raises(ValueError, match="http"):
        config_store.save_app_config("radarr", {"RADARR_URL": "http://user:pass@radarr:7878"})


def test_app_config_can_explicitly_clear_a_secret(monkeypatch, tmp_path):
    import os
    import homelabpilot.config_store as config_store

    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "app-config.enc")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-mcp-token-that-is-long-enough-123456")
    monkeypatch.setenv("RADARR_API_KEY", "old-secret")
    config_store.save_app_config("radarr", {}, clear_secrets=["RADARR_API_KEY"])
    assert os.environ["RADARR_API_KEY"] == ""
    secret = next(
        field for field in config_store.get_app_config()["radarr"]["fields"]
        if field["key"] == "RADARR_API_KEY"
    )
    assert secret["secret_set"] is False




@pytest.mark.parametrize(
    ("service", "expected_path", "expected_params"),
    [
        ("radarr", "/api/v3/history", {"page": 2, "pageSize": 25, "includeMovie": "true"}),
        ("sonarr", "/api/v3/history", {"page": 2, "pageSize": 25, "includeSeries": "true", "includeEpisode": "true"}),
        ("lidarr", "/api/v1/history", {"page": 2, "pageSize": 25, "includeArtist": "true", "includeAlbum": "true", "includeTrack": "true"}),
    ],
)
def test_arr_get_history_uses_service_specific_read_endpoint(monkeypatch, service, expected_path, expected_params):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_request(target, method, path, params=None, body=None, form_data=None):
        calls.append((target, method, path, params))
        return {"records": []}

    monkeypatch.setattr(server, "_arr_request", fake_request)
    assert asyncio.run(server.arr_get_history(service, page=2, page_size=25)) == {"records": []}
    assert calls == [(service, "GET", expected_path, expected_params)]


@pytest.mark.parametrize(
    ("service", "expected_path", "expected_params"),
    [
        ("radarr", "/api/v3/wanted/missing", {"page": 1, "pageSize": 40, "monitored": "true"}),
        ("sonarr", "/api/v3/wanted/missing", {"page": 1, "pageSize": 40, "monitored": "true", "includeSeries": "true"}),
        ("lidarr", "/api/v1/wanted/missing", {"page": 1, "pageSize": 40, "monitored": "true", "includeArtist": "true"}),
    ],
)
def test_arr_get_missing_items_uses_service_specific_read_endpoint(monkeypatch, service, expected_path, expected_params):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_request(target, method, path, params=None, body=None, form_data=None):
        calls.append((target, method, path, params))
        return {"records": []}

    monkeypatch.setattr(server, "_arr_request", fake_request)
    assert asyncio.run(server.arr_get_missing_items(service, page_size=40)) == {"records": []}
    assert calls == [(service, "GET", expected_path, expected_params)]


def test_arr_read_tools_reject_invalid_pagination():
    import asyncio
    import homelabpilot.server as server

    with pytest.raises(ValueError, match="page must be"):
        asyncio.run(server.arr_get_history("radarr", page=0))
    with pytest.raises(ValueError, match="page_size"):
        asyncio.run(server.arr_get_missing_items("sonarr", page_size=201))



def test_homeassistant_integration_uses_bearer_token_and_rest_healthcheck():
    from homelabpilot.integrations import HTTP_INTEGRATIONS
    from homelabpilot.config_store import APP_CONFIG_FIELDS

    assert HTTP_INTEGRATIONS["homeassistant"] == (
        "HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN", "bearer", "/api/"
    )
    assert APP_CONFIG_FIELDS["homeassistant"] == (
        "HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN"
    )



def test_pulsarr_authentication_and_api_endpoints_are_configured():
    from homelabpilot.integrations import HTTP_INTEGRATIONS

    assert HTTP_INTEGRATIONS["pulsarr"] == (
        "PULSARR_URL", "PULSARR_API_KEY", "x-api-key", "/health"
    )
    assert HTTP_INTEGRATIONS["cleanuparr"] == (
        "CLEANUPARR_URL", "CLEANUPARR_API_KEY", "x-api-key", "/health"
    )
    assert HTTP_INTEGRATIONS["maintainerr"] == (
        "MAINTAINERR_URL", "", "none", "/api/health/ready"
    )



def test_youtarr_external_api_uses_x_api_key_and_capabilities_healthcheck():
    from homelabpilot.integrations import HTTP_INTEGRATIONS
    from homelabpilot.config_store import APP_CONFIG_FIELDS

    assert HTTP_INTEGRATIONS["youtarr"] == (
        "YOUTARR_URL", "YOUTARR_API_KEY", "x-api-key", "/external-api/v1/capabilities"
    )
    assert APP_CONFIG_FIELDS["youtarr"] == ("YOUTARR_URL", "YOUTARR_API_KEY")


def test_tracearr_uses_bearer_auth_and_public_health_endpoint():
    from homelabpilot.integrations import HTTP_INTEGRATIONS
    from homelabpilot.config_store import APP_CONFIG_FIELDS

    assert HTTP_INTEGRATIONS["tracearr"] == (
        "TRACEARR_URL", "TRACEARR_API_KEY", "bearer", "/api/v1/public/health"
    )
    assert APP_CONFIG_FIELDS["tracearr"] == ("TRACEARR_URL", "TRACEARR_API_KEY")


def test_docker_control_requires_matching_preview_and_typed_confirmation(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_DOCKER_ENABLED", "true")
    monkeypatch.setenv("HOMELABPILOT_DOCKER_PERMISSION_LEVEL", "operations")
    monkeypatch.setenv("HOMELABPILOT_PREVIEW_SECRET", "p" * 40)

    with pytest.raises(PermissionError, match="preview"):
        asyncio.run(server.docker_control_allowlisted_container("radarr", "restart"))

    calls = []

    async def fake_gateway(method, path):
        calls.append((method, path))
        if method == "GET":
            return [{"name": "radarr", "id": "a" * 64}]
        return {"ok": True}

    monkeypatch.setattr(server, "_docker_gateway_request", fake_gateway)
    preview = asyncio.run(server.docker_preview_container_action("radarr", "restart"))
    assert preview["typed_confirmation"] == "CONFIRM DOCKER RESTART radarr"
    with pytest.raises(PermissionError, match="Type exactly"):
        asyncio.run(server.docker_control_allowlisted_container(
            "radarr", "restart", preview["preview_token"], "wrong phrase"
        ))

    result = asyncio.run(server.docker_control_allowlisted_container(
        "radarr", "restart", preview["preview_token"], preview["typed_confirmation"]
    ))
    assert result == {"ok": True}
    assert calls == [("GET", "/v1/containers"), ("POST", "/v1/containers/radarr/restart")]


def test_docker_preview_rejects_invalid_container_and_action(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_DOCKER_ENABLED", "true")
    monkeypatch.setenv("HOMELABPILOT_DOCKER_PERMISSION_LEVEL", "operations")
    monkeypatch.setenv("HOMELABPILOT_PREVIEW_SECRET", "p" * 40)

    with pytest.raises(ValueError, match="container"):
        asyncio.run(server.docker_preview_container_action("../radarr", "stop"))
    with pytest.raises(ValueError, match="action"):
        asyncio.run(server.docker_preview_container_action("radarr", "remove"))

    async def no_containers(method, path):
        return []

    monkeypatch.setattr(server, "_docker_gateway_request", no_containers)
    with pytest.raises(PermissionError, match="allowlist"):
        asyncio.run(server.docker_preview_container_action("radarr", "stop"))


def test_recyclarr_sync_requires_preview_and_exact_confirmation(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_DOCKER_ENABLED", "true")
    monkeypatch.setenv("HOMELABPILOT_DOCKER_PERMISSION_LEVEL", "operations")
    monkeypatch.setenv("HOMELABPILOT_PREVIEW_SECRET", "r" * 40)
    monkeypatch.setenv("RECYCLARR_CONTAINER", "recyclarr")
    calls = []

    async def fake_gateway(method, path):
        calls.append((method, path))
        if method == "GET":
            return [{"name": "recyclarr", "state": "running"}]
        return {"ok": True, "exit_code": 0}

    monkeypatch.setattr(server, "_docker_gateway_request", fake_gateway)
    monkeypatch.setattr(server, "_audit", lambda *args, **kwargs: None)

    preview = asyncio.run(server.recyclarr_preview_sync())
    assert preview["typed_confirmation"] == "CONFIRM RECYCLARR SYNC recyclarr"

    with pytest.raises(PermissionError, match="preview"):
        asyncio.run(server.recyclarr_confirm_sync("wrong", preview["typed_confirmation"]))

    result = asyncio.run(server.recyclarr_confirm_sync(
        preview["preview_token"], preview["typed_confirmation"]
    ))
    assert result["ok"] is True
    assert calls == [
        ("GET", "/v1/containers"),
        ("POST", "/v1/recyclarr/sync"),
    ]


def test_recyclarr_tools_require_configured_container(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_DOCKER_ENABLED", "true")
    monkeypatch.setenv("HOMELABPILOT_DOCKER_PERMISSION_LEVEL", "operations")
    monkeypatch.delenv("RECYCLARR_CONTAINER", raising=False)

    with pytest.raises(ValueError, match="RECYCLARR_CONTAINER"):
        asyncio.run(server.recyclarr_preview_sync())


def test_web_dashboard_reads_only_registered_integration_operations(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_dashboard_read(service, operation, **arguments):
        calls.append((service, operation, arguments))
        return {"service": service, "operation": operation}

    monkeypatch.setattr(server.integration_status, "dashboard_read", fake_dashboard_read)
    result = asyncio.run(server._web_api_request(
        "/web-api/integration/read", "POST", {},
        {"service": "frigate", "operation": "events", "arguments": {"limit": 10}},
    ))

    assert result == {"service": "frigate", "operation": "events"}
    assert calls == [("frigate", "events", {"limit": 10})]


def test_web_dashboard_recyclarr_routes_require_preview_and_confirmation(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    monkeypatch.setenv("HOMELABPILOT_DOCKER_ENABLED", "true")
    monkeypatch.setenv("HOMELABPILOT_DOCKER_PERMISSION_LEVEL", "operations")
    monkeypatch.setenv("HOMELABPILOT_PREVIEW_SECRET", "w" * 40)
    monkeypatch.setenv("RECYCLARR_CONTAINER", "recyclarr")
    monkeypatch.setattr(server, "_docker_gateway_request", lambda *args, **kwargs: None)

    async def fake_preview():
        return {"preview_token": "preview", "typed_confirmation": "CONFIRM RECYCLARR SYNC recyclarr"}

    async def fake_confirm(token, phrase):
        return {"ok": token == "preview" and phrase == "CONFIRM RECYCLARR SYNC recyclarr"}

    monkeypatch.setattr(server, "recyclarr_preview_sync", fake_preview)
    monkeypatch.setattr(server, "recyclarr_confirm_sync", fake_confirm)

    preview = asyncio.run(server._web_api_request("/web-api/recyclarr/preview", "POST", {}, {}))
    result = asyncio.run(server._web_api_request(
        "/web-api/recyclarr/confirm", "POST", {},
        {"preview_token": preview["preview_token"], "typed_confirmation": preview["typed_confirmation"]},
    ))
    assert result == {"ok": True}


def test_docker_dashboard_routes_forward_preview_confirmation(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def fake_preview(container, action):
        calls.append(("preview", container, action))
        return {"preview_token": "signed", "typed_confirmation": "CONFIRM DOCKER RESTART radarr"}

    async def fake_control(container, action, token, phrase):
        calls.append(("control", container, action, token, phrase))
        return {"ok": True}

    monkeypatch.setattr(server, "docker_preview_container_action", fake_preview)
    monkeypatch.setattr(server, "docker_control_allowlisted_container", fake_control)

    preview = asyncio.run(server._web_api_request(
        "/web-api/docker/preview", "POST", {}, {"container": "radarr", "action": "restart"}
    ))
    result = asyncio.run(server._web_api_request(
        "/web-api/docker/control", "POST", {},
        {
            "container": "radarr", "action": "restart",
            "preview_token": preview["preview_token"],
            "typed_confirmation": preview["typed_confirmation"],
        },
    ))

    assert result == {"ok": True}
    assert calls == [
        ("preview", "radarr", "restart"),
        ("control", "radarr", "restart", "signed", "CONFIRM DOCKER RESTART radarr"),
    ]


def test_mcp_bearer_middleware_rejects_missing_and_invalid_tokens():
    import asyncio
    import homelabpilot.server as server

    calls = []

    async def downstream(scope, receive, send):
        calls.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = server._BearerAuthMiddleware(downstream, "a-valid-test-token-with-more-than-32-chars")

    async def invoke(authorization):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        headers = [] if authorization is None else [(b"authorization", authorization.encode())]
        scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers}
        await middleware(scope, receive, send)
        return messages

    missing = asyncio.run(invoke(None))
    invalid = asyncio.run(invoke("Bearer wrong-token"))
    valid = asyncio.run(invoke("Bearer a-valid-test-token-with-more-than-32-chars"))

    assert missing[0]["status"] == 401
    assert invalid[0]["status"] == 401
    assert valid[0]["status"] == 200
    assert len(calls) == 1, "only the correctly authenticated request may reach the MCP app"


def test_stack_status_normalizes_qbittorrent_plain_text_version(monkeypatch):
    import asyncio
    import homelabpilot.server as server

    for url_env, key_env, _prefix in server.ARR_SERVICES.values():
        monkeypatch.delenv(url_env, raising=False)
        monkeypatch.delenv(key_env, raising=False)
    monkeypatch.setenv("QBITTORRENT_URL", "http://example.invalid")
    monkeypatch.setenv("QBITTORRENT_USERNAME", "test")
    monkeypatch.setenv("QBITTORRENT_PASSWORD", "test")

    async def fake_qbittorrent(method, path, params=None, data=None):
        assert method == "GET"
        assert path == "/api/v2/app/version"
        return {"http_status": 200, "text": "v5.1.2"}

    async def no_integrations():
        return {}

    monkeypatch.setattr(server, "qbittorrent_api_request", fake_qbittorrent)
    monkeypatch.setattr(server, "integration_status", no_integrations)

    result = asyncio.run(server.stack_status())
    assert result["services"]["qbittorrent"]["ok"] is True
    assert result["services"]["qbittorrent"]["version"] == "v5.1.2"
