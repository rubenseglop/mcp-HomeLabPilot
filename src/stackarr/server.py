"""StackARR MCP: full-control API bridge for media applications.

The server never accepts a caller-supplied hostname. Requests are restricted to
service base URLs configured by the operator, preventing the MCP tools from
becoming a general-purpose HTTP proxy.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP
import uvicorn

from stackarr.web import StackARRWebMiddleware

mcp = FastMCP("StackARR")
TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))

MCP_PERMISSION_LEVELS = {"read": 0, "operations": 1, "admin": 2}


def _require_permission(required: str) -> None:
    """Enforce the configured permission tier for MCP write operations."""
    configured = os.getenv("STACKARR_MCP_PERMISSION_LEVEL", "operations").strip().lower()
    if configured not in MCP_PERMISSION_LEVELS:
        raise RuntimeError(
            "STACKARR_MCP_PERMISSION_LEVEL must be read, operations or admin"
        )
    if required not in MCP_PERMISSION_LEVELS:
        raise RuntimeError(f"Unknown internal permission tier: {required}")
    if MCP_PERMISSION_LEVELS[configured] < MCP_PERMISSION_LEVELS[required]:
        raise PermissionError(
            f"This action requires '{required}' permission; current level is '{configured}'"
        )


def _arr_api_required_permission(method: str, path: str) -> str:
    """Classify generic ARR API writes without allowing destructive bypasses."""
    method = method.upper()
    if method == "GET":
        return "read"
    normalized = path.lower()
    admin_fragments = (
        "/qualityprofile", "/delayprofile", "/indexer", "/downloadclient",
        "/notification", "/config/", "/system/",
    )
    if method == "DELETE" or any(fragment in normalized for fragment in admin_fragments):
        return "admin"
    return "operations"

ARR_SERVICES = {
    "radarr": ("RADARR_URL", "RADARR_API_KEY", "/api/v3"),
    "sonarr": ("SONARR_URL", "SONARR_API_KEY", "/api/v3"),
    "prowlarr": ("PROWLARR_URL", "PROWLARR_API_KEY", "/api/v1"),
    "bazarr": ("BAZARR_URL", "BAZARR_API_KEY", "/api"),
}


def _base_url(env_name: str) -> str:
    value = os.getenv(env_name, "").strip().rstrip("/")
    if not value:
        raise ValueError(f"Missing configuration: {env_name}")
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"{env_name} must be an http:// or https:// URL")
    return value


def _safe_path(path: str) -> str:
    """Accept API paths only, never absolute URLs or protocol-relative URLs."""
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "://" in path
        or "\\" in path
        or any(segment == ".." for segment in path.split("/"))
        or any(ord(char) < 32 for char in path)
    ):
        raise ValueError("path must be a safe API path beginning with one '/'")
    return path


def _decode_response(response: httpx.Response) -> Any:
    if not response.content:
        return {"http_status": response.status_code}
    try:
        return response.json()
    except ValueError:
        return {"http_status": response.status_code, "text": response.text[:12000]}


async def _arr_request(
    service: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> Any:
    if service not in ARR_SERVICES:
        raise ValueError(f"Unsupported service '{service}'. Choose: {', '.join(ARR_SERVICES)}")
    url_env, key_env, _ = ARR_SERVICES[service]
    base = _base_url(url_env)
    api_key = os.getenv(key_env, "").strip()
    if not api_key:
        raise ValueError(f"Missing configuration: {key_env}")
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("method must be GET, POST, PUT, PATCH or DELETE")
    endpoint = urljoin(base + "/", _safe_path(path).lstrip("/"))
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        response = await client.request(
            method,
            endpoint,
            params=params,
            json=body,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
        )
        response.raise_for_status()
        return _decode_response(response)


@mcp.tool()
async def arr_api_request(
    service: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> Any:
    """Control Radarr, Sonarr, Prowlarr or Bazarr through its native REST API.

    Supports GET/POST/PUT/PATCH/DELETE. Use the service's API path, e.g.
    Radarr/Sonarr /api/v3/movie, /api/v3/command; Prowlarr /api/v1/indexer;
    Bazarr /api/... . The configured host and API key are used automatically.
    """
    _require_permission(_arr_api_required_permission(method, path))
    return await _arr_request(service, method, path, params, body)


@mcp.tool()
async def scryer_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
) -> Any:
    """Execute a Scryer GraphQL query or mutation using its API key.

    Supports the full Scryer GraphQL API, including title/library management,
    acquisition searches, release grabs, requests, subtitles, indexers,
    download clients, settings and job controls. Use documented GraphQL
    operations and inputs for the installed Scryer version.
    """
    if re.search(r"\bmutation\b", query, re.IGNORECASE):
        _require_permission("admin")
    base = _base_url("SCRYER_URL")
    token = os.getenv("SCRYER_API_KEY", "").strip()
    if not token:
        raise ValueError("Missing configuration: SCRYER_API_KEY")
    payload: dict[str, Any] = {"query": query, "variables": variables or {}}
    if operation_name:
        payload["operationName"] = operation_name
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        response = await client.post(
            urljoin(base + "/", "graphql"),
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        response.raise_for_status()
        return _decode_response(response)


def _check_qbittorrent_login(response: httpx.Response) -> None:
    """Accept qBittorrent's successful WebUI login response variants."""
    response.raise_for_status()
    # Depending on qBittorrent version, a successful login returns either
    # HTTP 200 with "Ok." or HTTP 204 with an empty response body.
    if response.status_code == 204:
        return
    if response.status_code == 200 and response.text.strip() == "Ok.":
        return
    raise RuntimeError("qBittorrent rejected the configured credentials")


async def qbittorrent_api_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> Any:
    """Control qBittorrent through its Web API (pause, resume, add, remove, etc.).

    Supports GET/POST/PUT/DELETE under /api/v2/. The configured WebUI account
    is authenticated automatically. For POST operations, provide form fields
    in data; torrent file uploads are not yet supported by this tool.
    """
    base = _base_url("QBITTORRENT_URL")
    username = os.getenv("QBITTORRENT_USERNAME", "")
    password = os.getenv("QBITTORRENT_PASSWORD", "")
    if not username or not password:
        raise ValueError("Missing qBittorrent username/password configuration")
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "DELETE"}:
        raise ValueError("method must be GET, POST, PUT or DELETE")
    path = _safe_path(path)
    if not path.startswith("/api/v2/"):
        raise ValueError("qBittorrent path must be under /api/v2/")
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        login = await client.post(
            f"{base}/api/v2/auth/login",
            data={"username": username, "password": password},
        )
        _check_qbittorrent_login(login)
        response = await client.request(
            method, f"{base}{path}", params=params, data=data
        )
        response.raise_for_status()
        return _decode_response(response)


@mcp.tool()
async def stack_status() -> dict[str, Any]:
    """Check configured services and report their API status/version."""
    checks: dict[str, Any] = {}
    for service, (url_env, _, api_prefix) in ARR_SERVICES.items():
        try:
            payload = await _arr_request(service, "GET", f"{api_prefix}/system/status")
            checks[service] = {
                "ok": True,
                "version": payload.get("version") if isinstance(payload, dict) else None,
                "app_name": payload.get("appName") if isinstance(payload, dict) else None,
            }
        except Exception as exc:
            checks[service] = {"ok": False, "error": str(exc)}
    try:
        result = await scryer_graphql("query StackStatus { scryerVersion }")
        checks["scryer"] = {"ok": "errors" not in result, "result": result}
    except Exception as exc:
        checks["scryer"] = {"ok": False, "error": str(exc)}
    try:
        version = await qbittorrent_api_request("GET", "/api/v2/app/version")
        checks["qbittorrent"] = {"ok": True, "version": version}
    except Exception as exc:
        checks["qbittorrent"] = {"ok": False, "error": str(exc)}
    return {"services": checks}



ARR_EDITABLE_RESOURCES = {
    "qualityprofile": "/api/v3/qualityprofile",
    "delayprofile": "/api/v3/delayprofile",
    "indexer": "/api/v3/indexer",
    "downloadclient": "/api/v3/downloadclient",
    "notification": "/api/v3/notification",
}

ARR_EDITABLE_RESOURCES_BY_SERVICE = {
    "radarr": ARR_EDITABLE_RESOURCES,
    "sonarr": ARR_EDITABLE_RESOURCES,
    "prowlarr": {
        "indexer": "/api/v1/indexer",
        "downloadclient": "/api/v1/downloadclient",
        "notification": "/api/v1/notification",
    },
}
SENSITIVE_CONFIG_KEY = re.compile(
    r'(?:password|passwd|api.?key|token|secret|credential|auth.?key|private.?key)',
    re.IGNORECASE,
)

def _is_sensitive_config_key(key: Any) -> bool:
    return isinstance(key, str) and bool(SENSITIVE_CONFIG_KEY.search(key))

def _redact_sensitive_config(value: Any) -> Any:
    """Remove secret values before configuration reaches MCP clients or browsers."""
    if isinstance(value, dict):
        result = {}
        sensitive_field = _is_sensitive_config_key(value.get("name"))
        for key, child in value.items():
            if _is_sensitive_config_key(key) or (sensitive_field and key == "value"):
                continue
            result[key] = _redact_sensitive_config(child)
        return result
    if isinstance(value, list):
        return [_redact_sensitive_config(item) for item in value]
    return value

def _restore_sensitive_config(current: Any, submitted: Any) -> Any:
    """Preserve secret fields omitted by clients when saving a redacted object."""
    if isinstance(current, dict) and isinstance(submitted, dict):
        merged = dict(submitted)
        sensitive_field = _is_sensitive_config_key(current.get("name"))
        for key, old_value in current.items():
            if _is_sensitive_config_key(key) or (sensitive_field and key == "value"):
                merged[key] = old_value
            elif key in merged:
                merged[key] = _restore_sensitive_config(old_value, merged[key])
        return merged
    if isinstance(current, list) and isinstance(submitted, list):
        return [_restore_sensitive_config(old, submitted[index]) if index < len(submitted) else old for index, old in enumerate(current)]
    return submitted

QBITTORRENT_EDITABLE_PREFERENCES = {
    "save_path", "temp_path", "temp_path_enabled", "scan_dirs",
    "max_active_downloads", "max_active_uploads", "max_active_torrents",
    "max_connections", "max_connections_per_torrent",
    "max_uploads", "max_uploads_per_torrent",
    "dl_limit", "up_limit", "alt_speed_enabled",
}


@mcp.tool()
async def arr_get_configuration(service: str, resource: str) -> Any:
    """Read editable configuration records from Radarr, Sonarr or Prowlarr."""
    resources = ARR_EDITABLE_RESOURCES_BY_SERVICE.get(service)
    if resources is None:
        raise ValueError("service must be radarr, sonarr or prowlarr")
    if resource not in resources:
        raise ValueError(f"resource for {service} must be one of: {', '.join(resources)}")
    result = await _arr_request(service, "GET", resources[resource])
    return _redact_sensitive_config(result)


@mcp.tool()
async def arr_update_configuration(service: str, resource: str, item_id: int, item: dict[str, Any]) -> Any:
    """Update an existing editable configuration record in Radarr, Sonarr or Prowlarr."""
    _require_permission("admin")
    resources = ARR_EDITABLE_RESOURCES_BY_SERVICE.get(service)
    if resources is None:
        raise ValueError("service must be radarr, sonarr or prowlarr")
    if resource not in resources:
        raise ValueError(f"resource for {service} must be one of: {', '.join(resources)}")
    if item_id < 1 or not isinstance(item, dict) or int(item.get("id", 0)) != item_id:
        raise ValueError("item must be an object whose id matches the positive item_id")
    endpoint = resources[resource]
    current = await _arr_request(service, "GET", f"{endpoint}/{item_id}")
    safe_item = _restore_sensitive_config(current, item)
    return await _arr_request(service, "PUT", f"{endpoint}/{item_id}", body=safe_item)


@mcp.tool()
async def qbittorrent_get_preferences() -> dict[str, Any]:
    """Read a safe allowlist of qBittorrent download and connection preferences."""
    prefs = await qbittorrent_api_request("GET", "/api/v2/app/preferences")
    if not isinstance(prefs, dict):
        raise RuntimeError("qBittorrent returned an unexpected preferences response")
    return {key: value for key, value in prefs.items() if key in QBITTORRENT_EDITABLE_PREFERENCES}


@mcp.tool()
async def qbittorrent_update_preferences(preferences: dict[str, Any]) -> Any:
    """Update allowlisted qBittorrent download paths, speed limits and queue/connection settings."""
    _require_permission("admin")
    if not isinstance(preferences, dict) or not preferences:
        raise ValueError("preferences must be a non-empty object")
    unknown = set(preferences) - QBITTORRENT_EDITABLE_PREFERENCES
    if unknown:
        raise ValueError(f"Unsupported qBittorrent preferences: {', '.join(sorted(unknown))}")
    import json
    return await qbittorrent_api_request(
        "POST", "/api/v2/app/setPreferences",
        data={"json": json.dumps(preferences)},
    )


@mcp.tool()
async def arr_list_library(service: str) -> Any:
    """List the movie or series library in Radarr or Sonarr."""
    if service == "radarr":
        path = "/api/v3/movie"
    elif service == "sonarr":
        path = "/api/v3/series"
    else:
        raise ValueError("service must be radarr or sonarr")
    return await _arr_request(service, "GET", path)


@mcp.tool()
async def arr_update_library_item(
    service: str,
    item_id: int,
    monitored: bool | None = None,
    quality_profile_id: int | None = None,
) -> Any:
    """Update monitoring and/or quality profile for an existing Radarr movie or Sonarr series."""
    _require_permission("operations")
    if service not in {"radarr", "sonarr"}:
        raise ValueError("service must be radarr or sonarr")
    if item_id < 1:
        raise ValueError("item_id must be positive")
    if monitored is None and quality_profile_id is None:
        raise ValueError("At least one of monitored or quality_profile_id must be provided")
    if quality_profile_id is not None and quality_profile_id < 1:
        raise ValueError("quality_profile_id must be positive")
    resource = "movie" if service == "radarr" else "series"
    endpoint = f"/api/v3/{resource}/{item_id}"
    current = await _arr_request(service, "GET", endpoint)
    if not isinstance(current, dict) or int(current.get("id", 0)) != item_id:
        raise RuntimeError(f"{service} returned an unexpected library item")
    updated = dict(current)
    if monitored is not None:
        updated["monitored"] = monitored
    if quality_profile_id is not None:
        updated["qualityProfileId"] = quality_profile_id
    return await _arr_request(service, "PUT", endpoint, body=updated)


@mcp.tool()
async def arr_search_catalog(service: str, term: str) -> Any:
    """Search Radarr movie metadata or Sonarr series metadata by title."""
    if not term.strip():
        raise ValueError("term cannot be empty")
    if service == "radarr":
        path = "/api/v3/movie/lookup"
    elif service == "sonarr":
        path = "/api/v3/series/lookup"
    else:
        raise ValueError("service must be radarr or sonarr")
    return await _arr_request(service, "GET", path, params={"term": term.strip()})


@mcp.tool()
async def arr_get_queue(service: str, page: int = 1, page_size: int = 50) -> Any:
    """Inspect the current download/import queue in Radarr or Sonarr."""
    if service not in {"radarr", "sonarr"}:
        raise ValueError("service must be radarr or sonarr")
    if page < 1 or page_size < 1 or page_size > 200:
        raise ValueError("page must be >= 1 and page_size between 1 and 200")
    return await _arr_request(
        service, "GET", "/api/v3/queue",
        params={"page": page, "pageSize": page_size, "includeUnknownSeriesItems": "true"},
    )


@mcp.tool()
async def arr_get_setup_options(service: str) -> dict[str, Any]:
    """Get root folders and quality profiles needed when adding movies or series."""
    if service not in {"radarr", "sonarr"}:
        raise ValueError("service must be radarr or sonarr")
    root_path = "/api/v3/rootfolder"
    profile_path = "/api/v3/qualityprofile"
    roots, profiles = await asyncio.gather(
        _arr_request(service, "GET", root_path),
        _arr_request(service, "GET", profile_path),
    )
    return {"root_folders": roots, "quality_profiles": profiles}


@mcp.tool()
async def arr_add_movie(
    tmdb_id: int,
    root_folder_path: str,
    quality_profile_id: int,
    monitored: bool = True,
    search_now: bool = False,
) -> Any:
    """Add a TMDB movie to Radarr. Get valid root folders/profile IDs with arr_get_setup_options first."""
    _require_permission("operations")
    if tmdb_id < 1 or not root_folder_path.startswith("/"):
        raise ValueError("tmdb_id must be positive and root_folder_path must be absolute")
    payload = {
        "tmdbId": tmdb_id,
        "rootFolderPath": root_folder_path,
        "qualityProfileId": quality_profile_id,
        "monitored": monitored,
        "addOptions": {"searchForMovie": search_now},
    }
    return await _arr_request("radarr", "POST", "/api/v3/movie", body=payload)


@mcp.tool()
async def arr_add_series(
    tvdb_id: int,
    root_folder_path: str,
    quality_profile_id: int,
    language_profile_id: int = 1,
    monitored: bool = True,
    search_now: bool = False,
) -> Any:
    """Add a TVDB series to Sonarr. Get valid root folders/profile IDs with arr_get_setup_options first."""
    _require_permission("operations")
    if tvdb_id < 1 or not root_folder_path.startswith("/"):
        raise ValueError("tvdb_id must be positive and root_folder_path must be absolute")
    payload = {
        "tvdbId": tvdb_id,
        "rootFolderPath": root_folder_path,
        "qualityProfileId": quality_profile_id,
        "languageProfileId": language_profile_id,
        "monitored": monitored,
        "addOptions": {"searchForCutoffUnmetEpisodes": search_now},
    }
    return await _arr_request("sonarr", "POST", "/api/v3/series", body=payload)


@mcp.tool()
async def arr_search_releases(service: str, item_id: int) -> Any:
    """Search available releases for a Radarr movie or Sonarr series."""
    if item_id < 1:
        raise ValueError("item_id must be positive")
    if service == "radarr":
        return await _arr_request("radarr", "GET", "/api/v3/release", params={"movieId": item_id})
    if service == "sonarr":
        return await _arr_request("sonarr", "GET", "/api/v3/release", params={"seriesId": item_id})
    raise ValueError("service must be radarr or sonarr")


@mcp.tool()
async def arr_grab_release(service: str, guid: str, indexer_id: int) -> Any:
    """Send a selected release to the configured download client through Radarr or Sonarr."""
    _require_permission("operations")
    if service not in {"radarr", "sonarr"}:
        raise ValueError("service must be radarr or sonarr")
    if not guid.strip() or indexer_id < 1:
        raise ValueError("guid and positive indexer_id are required")
    return await _arr_request(
        service, "POST", "/api/v3/release",
        body={"guid": guid, "indexerId": indexer_id},
    )


@mcp.tool()
async def scryer_introspect() -> Any:
    """Discover Scryer's live GraphQL query and mutation fields and their arguments."""
    query = """
    query StackARRSchema {
      __schema {
        queryType { name fields { name description args { name type { kind name ofType { kind name ofType { kind name } } } } } }
        mutationType { name fields { name description args { name type { kind name ofType { kind name ofType { kind name } } } } } }
      }
    }
    """
    return await scryer_graphql(query)


@mcp.tool()
async def qbittorrent_list_torrents(
    filter: str = "all",
    category: str | None = None,
    tag: str | None = None,
    sort: str = "added_on",
    reverse: bool = True,
    limit: int = 100,
) -> Any:
    """List qBittorrent torrents, optionally filtered by state, category or tag."""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    params: dict[str, Any] = {"filter": filter, "sort": sort, "reverse": str(reverse).lower(), "limit": limit}
    if category:
        params["category"] = category
    if tag:
        params["tag"] = tag
    return await qbittorrent_api_request("GET", "/api/v2/torrents/info", params=params)


@mcp.tool()
async def qbittorrent_control_torrents(action: str, hashes: str) -> Any:
    """Pause, resume, recheck or reannounce selected torrents using comma-separated hashes."""
    _require_permission("operations")
    endpoints = {
        "pause": "/api/v2/torrents/pause",
        "resume": "/api/v2/torrents/resume",
        "recheck": "/api/v2/torrents/recheck",
        "reannounce": "/api/v2/torrents/reannounce",
    }
    if action not in endpoints:
        raise ValueError(f"action must be one of: {', '.join(endpoints)}")
    if not hashes.strip():
        raise ValueError("hashes cannot be empty")
    return await qbittorrent_api_request("POST", endpoints[action], data={"hashes": hashes})


@mcp.tool()
async def qbittorrent_delete_torrents(hashes: str, delete_files: bool = False) -> Any:
    """Remove torrents. Set delete_files=true only when the user explicitly wants data files deleted too."""
    _require_permission("admin")
    if not hashes.strip():
        raise ValueError("hashes cannot be empty")
    return await qbittorrent_api_request(
        "POST", "/api/v2/torrents/delete",
        data={"hashes": hashes, "deleteFiles": str(delete_files).lower()},
    )


@mcp.tool()
async def qbittorrent_set_category(hashes: str, category: str) -> Any:
    """Assign one qBittorrent category to selected torrents."""
    _require_permission("operations")
    if not hashes.strip() or not category.strip():
        raise ValueError("hashes and category are required")
    return await qbittorrent_api_request(
        "POST", "/api/v2/torrents/setCategory",
        data={"hashes": hashes, "category": category},
    )


class _BearerAuthMiddleware:
    """Protect the remote MCP endpoint with a constant-time bearer-token check."""

    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"").decode("utf-8", "ignore")
        expected = "Bearer " + self.token.decode("utf-8")
        if not hmac.compare_digest(supplied, expected):
            body = b'{"error":"Unauthorized"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


async def _web_api_request(
    path: str, method: str, query: dict[str, list[str]], payload: dict[str, Any]
) -> Any:
    """Shared browser API actions; all service calls reuse the same configured API layer."""
    if method == "GET" and path == "/web-api/catalog":
        service = (query.get("service") or [""])[0]
        term = (query.get("term") or [""])[0]
        return await arr_search_catalog(service, term)
    if method == "GET" and path == "/web-api/setup":
        service = (query.get("service") or [""])[0]
        return await arr_get_setup_options(service)
    if method == "POST" and path == "/web-api/catalog/add":
        service = str(payload.get("service", ""))
        monitored = bool(payload.get("monitored", True))
        search_now = bool(payload.get("search_now", False))
        if service == "radarr":
            return await arr_add_movie(
                int(payload.get("tmdb_id", 0)), str(payload.get("root_folder_path", "")),
                int(payload.get("quality_profile_id", 0)), monitored, search_now,
            )
        if service == "sonarr":
            return await arr_add_series(
                int(payload.get("tvdb_id", 0)), str(payload.get("root_folder_path", "")),
                int(payload.get("quality_profile_id", 0)), monitored=monitored, search_now=search_now,
            )
        raise ValueError("service must be radarr or sonarr")

    if method == "GET" and path == "/web-api/settings":
        service = (query.get("service") or [""])[0]
        resource = (query.get("resource") or [""])[0]
        if service == "qbittorrent":
            return await qbittorrent_get_preferences()
        return await arr_get_configuration(service, resource)
    if method == "POST" and path == "/web-api/settings/update":
        service = str(payload.get("service", ""))
        if service == "qbittorrent":
            return await qbittorrent_update_preferences(payload.get("preferences", {}))
        return await arr_update_configuration(
            service, str(payload.get("resource", "")),
            int(payload.get("id", 0)), payload.get("item", {}),
        )
    if method == "POST" and path == "/web-api/library/update":
        service = str(payload.get("service", ""))
        item_id = int(payload.get("id", 0))
        monitored = payload.get("monitored") if "monitored" in payload else None
        profile_id = payload.get("quality_profile_id")
        return await arr_update_library_item(
            service, item_id, monitored=monitored,
            quality_profile_id=int(profile_id) if profile_id is not None else None,
        )
    if method == "GET" and path == "/web-api/releases":
        service = (query.get("service") or [""])[0]
        item_id = int((query.get("id") or ["0"])[0])
        return await arr_search_releases(service, item_id)
    if method == "POST" and path == "/web-api/releases/grab":
        return await arr_grab_release(
            str(payload.get("service", "")),
            str(payload.get("guid", "")),
            int(payload.get("indexer_id", 0)),
        )
    if method == "GET" and path == "/web-api/library":
        service = (query.get("service") or [""])[0]
        return await arr_list_library(service)
    if method == "GET" and path == "/web-api/queue":
        service = (query.get("service") or [""])[0]
        return await arr_get_queue(service)
    if method == "GET" and path == "/web-api/torrents":
        return await qbittorrent_list_torrents(limit=200)
    if method == "POST" and path == "/web-api/torrents/control":
        action = str(payload.get("action", ""))
        hashes = str(payload.get("hashes", ""))
        return await qbittorrent_control_torrents(action, hashes)
    raise ValueError("Unknown StackARR web API operation")


def main() -> None:
    """Run StackARR over stdio (default) or authenticated Streamable HTTP."""
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    if transport != "streamable-http":
        raise ValueError("MCP_TRANSPORT must be 'stdio' or 'streamable-http'")
    token = os.getenv("MCP_AUTH_TOKEN", "").strip()
    if len(token) < 32:
        raise ValueError("MCP_AUTH_TOKEN must contain at least 32 characters for HTTP mode")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    app = _BearerAuthMiddleware(mcp.streamable_http_app(), token)
    web_username = os.getenv("STACKARR_WEB_USERNAME", "admin").strip() or "admin"
    web_password = os.getenv("STACKARR_WEB_PASSWORD", "").strip() or token
    app = StackARRWebMiddleware(
        app, token, stack_status, _web_api_request,
        web_username=web_username, web_password=web_password,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
