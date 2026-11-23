"""HomeLabPilot MCP: full-control API bridge for media applications.

The server never accepts a caller-supplied hostname. Requests are restricted to
service base URLs configured by the operator, preventing the MCP tools from
becoming a general-purpose HTTP proxy.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import uvicorn

from homelabpilot.audit import list_events as list_audit_events, record_event
from homelabpilot.web import HomeLabPilotWebMiddleware
from homelabpilot.integrations import register_integration_tools
from homelabpilot.seanime import register_seanime_tools
from homelabpilot.config_store import get_app_config, load_saved_config, save_app_config

load_saved_config()

TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
_AUDIT_SOURCE: ContextVar[str] = ContextVar("homelabpilot_audit_source", default="mcp")


def _mcp_allowed_hosts() -> list[str]:
    """Read the explicit Host allowlist for the MCP HTTP transport."""
    hosts = [
        value.strip()
        for value in os.getenv(
            "HOMELABPILOT_MCP_ALLOWED_HOSTS",
            "localhost:*,127.0.0.1:*,[::1]:*",
        ).split(",")
        if value.strip()
    ]
    if not hosts:
        raise ValueError("HOMELABPILOT_MCP_ALLOWED_HOSTS must contain at least one host pattern")
    return hosts


mcp = FastMCP(
    "HomeLabPilot",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    transport_security=TransportSecuritySettings(allowed_hosts=_mcp_allowed_hosts()),
)

MCP_PERMISSION_LEVELS = {"read": 0, "operations": 1, "admin": 2}


def _require_permission(required: str) -> None:
    """Enforce the configured permission tier for MCP write operations."""
    configured = os.getenv("HOMELABPILOT_MCP_PERMISSION_LEVEL", "operations").strip().lower()
    if configured not in MCP_PERMISSION_LEVELS:
        raise RuntimeError(
            "HOMELABPILOT_MCP_PERMISSION_LEVEL must be read, operations or admin"
        )
    if required not in MCP_PERMISSION_LEVELS:
        raise RuntimeError(f"Unknown internal permission tier: {required}")
    if MCP_PERMISSION_LEVELS[configured] < MCP_PERMISSION_LEVELS[required]:
        raise PermissionError(
            f"This action requires '{required}' permission; current level is '{configured}'"
        )


def _audit(operation: str, service: str = "homelabpilot", target: str = "", outcome: str = "succeeded") -> None:
    record_event(operation, service=service, target=target, outcome=outcome, source=_AUDIT_SOURCE.get())


def _preview_token(snapshot: Any) -> str:
    """Bind a destructive confirmation to a current snapshot without exposing its contents."""
    secret = (os.getenv("HOMELABPILOT_PREVIEW_SECRET") or os.getenv("MCP_AUTH_TOKEN") or "").strip()
    if len(secret) < 32:
        raise ValueError("Set HOMELABPILOT_PREVIEW_SECRET or a 32-character MCP_AUTH_TOKEN for delete previews")
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()


def _arr_api_required_permission(method: str, path: str) -> str:
    """Classify generic ARR API writes without allowing destructive bypasses."""
    method = method.upper()
    if method == "GET":
        return "read"
    normalized = path.lower()
    admin_fragments = (
        "/qualityprofile", "/qualitydefinition", "/delayprofile", "/metadataprofile",
        "/customformat", "/importlist", "/metadata", "/tag",
        "/languageprofile", "/releaseprofile", "/indexer", "/downloadclient",
        "/notification", "/provider", "/providers", "/config/", "/system/",
        "/command", "/bulk", "/settings", "/application", "/rootfolder", "/auth/",
        "/releaseprofile", "/autotagging", "/remotepathmapping",
    )
    if method == "DELETE" or any(fragment in normalized for fragment in admin_fragments):
        return "admin"
    return "operations"

ARR_SERVICES = {
    "radarr": ("RADARR_URL", "RADARR_API_KEY", "/api/v3"),
    "sonarr": ("SONARR_URL", "SONARR_API_KEY", "/api/v3"),
    "prowlarr": ("PROWLARR_URL", "PROWLARR_API_KEY", "/api/v1"),
    "bazarr": ("BAZARR_URL", "BAZARR_API_KEY", "/api"),
    "lidarr": ("LIDARR_URL", "LIDARR_API_KEY", "/api/v1"),
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
    form_data: dict[str, Any] | None = None,
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
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.request(
                method,
                endpoint,
                params=params,
                json=body if form_data is None else None,
                data=form_data,
                headers={"X-Api-Key": api_key, "Accept": "application/json"},
            )
            response.raise_for_status()
            result = _decode_response(response)
    except Exception:
        if method != "GET":
            _audit(method, service, path, "failed")
        raise
    if method != "GET":
        _audit(method, service, path)
    return result


@mcp.tool()
async def arr_api_request(
    service: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> Any:
    """Control Radarr, Sonarr, Prowlarr, Bazarr or Lidarr through its native REST API.

    Supports GET/POST/PUT/PATCH/DELETE. Use each service's native API path;
    the configured host and API key are supplied automatically.
    """
    _require_permission(_arr_api_required_permission(method, path))
    normalized_path = path.lower()
    if method.upper() == "DELETE":
        raise PermissionError("Direct ARR DELETE requests are disabled; use a preview and typed confirmation")
    if method.upper() != "GET" and "/command" in normalized_path:
        raise PermissionError("Generic ARR command requests are disabled; use a dedicated HomeLabPilot workflow")
    return await _arr_request(service, method, path, params, body)


async def _scryer_request(
    query: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
    *,
    allow_destructive: bool = False,
) -> Any:
    is_mutation = bool(re.search(r"\bmutation\b", query, re.IGNORECASE))
    destructive = is_mutation and bool(
        re.search(r"\b(?:delete[A-Z]\w*|emptyRecycleBin)\s*\(", query)
    )
    if is_mutation:
        _require_permission("admin")
    if destructive and not allow_destructive:
        raise PermissionError(
            "Destructive Scryer mutations require a dedicated preview and confirmation workflow"
        )
    base = _base_url("SCRYER_URL")
    token = os.getenv("SCRYER_API_KEY", "").strip()
    if not token:
        raise ValueError("Missing configuration: SCRYER_API_KEY")
    payload: dict[str, Any] = {"query": query, "variables": variables or {}}
    if operation_name:
        payload["operationName"] = operation_name
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.post(
                urljoin(base + "/", "graphql"),
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            result = _decode_response(response)
    except Exception:
        if is_mutation:
            _audit(operation_name or "GraphQL mutation", "scryer", outcome="failed")
        raise
    if is_mutation:
        operation = operation_name or re.search(
            r"\b(?:delete[A-Z]\w*|emptyRecycleBin|[A-Za-z_]\w*)\s*\(", query
        )
        if isinstance(operation, re.Match):
            operation = operation.group(0).split("(", 1)[0].strip()
        failed = isinstance(result, dict) and bool(result.get("errors"))
        _audit(str(operation or "GraphQL mutation"), "scryer", outcome="failed" if failed else "succeeded")
    return result


@mcp.tool()
async def scryer_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
) -> Any:
    """Run Scryer GraphQL queries/mutations; destructive fields require dedicated preview tools."""
    return await _scryer_request(query, variables, operation_name)


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
    try:
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
            result = _decode_response(response)
    except Exception:
        if method != "GET":
            _audit(method, "qbittorrent", path, "failed")
        raise
    if method != "GET":
        _audit(method, "qbittorrent", path)
    return result


integration_status = register_integration_tools(
    mcp=mcp,
    require_permission=_require_permission,
    make_preview_token=_preview_token,
    safe_path=_safe_path,
    base_url=_base_url,
    decode_response=_decode_response,
    audit=_audit,
    timeout=TIMEOUT,
)

register_seanime_tools(mcp=mcp, timeout=TIMEOUT, audit=_audit)

@mcp.tool()
async def stack_status() -> dict[str, Any]:
    """Check configured services and report their API status/version."""
    checks: dict[str, Any] = {}
    for service, (url_env, key_env, api_prefix) in ARR_SERVICES.items():
        configured = bool(os.getenv(url_env, "").strip() and os.getenv(key_env, "").strip())
        if not configured:
            checks[service] = {"configured": False, "ok": False}
            continue
        try:
            payload = await _arr_request(service, "GET", f"{api_prefix}/system/status")
            checks[service] = {
                "configured": True,
                "ok": True,
                "version": payload.get("version") if isinstance(payload, dict) else None,
                "app_name": payload.get("appName") if isinstance(payload, dict) else None,
            }
        except Exception:
            checks[service] = {
                "configured": True,
                "ok": False,
                "error": f"{service} is configured but its status check failed; verify its URL and API key",
            }
    scryer_configured = bool(
        os.getenv("SCRYER_URL", "").strip() and os.getenv("SCRYER_API_KEY", "").strip()
    )
    if not scryer_configured:
        checks["scryer"] = {"configured": False, "ok": False}
    else:
        try:
            result = await scryer_graphql("query StackStatus { scryerVersion }")
            checks["scryer"] = {
                "configured": True, "ok": "errors" not in result, "result": result
            }
        except Exception:
            checks["scryer"] = {
                "configured": True, "ok": False,
                "error": "Scryer is configured but its status check failed; verify its URL and API key",
            }
    qbit_configured = bool(os.getenv("QBITTORRENT_URL", "").strip())
    if not qbit_configured:
        checks["qbittorrent"] = {"configured": False, "ok": False}
    else:
        try:
            version = await qbittorrent_api_request("GET", "/api/v2/app/version")
            checks["qbittorrent"] = {"configured": True, "ok": True, "version": version}
        except Exception:
            checks["qbittorrent"] = {
                "configured": True, "ok": False,
                "error": "qBittorrent is configured but its status check failed; verify its URL and credentials",
            }
    checks.update(await integration_status())
    return {"services": checks}



ARR_EDITABLE_RESOURCES = {
    # Native configuration records shared by Radarr and Sonarr.
    "qualityprofile": "/api/v3/qualityprofile",
    "delayprofile": "/api/v3/delayprofile",
    "indexer": "/api/v3/indexer",
    "downloadclient": "/api/v3/downloadclient",
    "notification": "/api/v3/notification",
    "qualitydefinition": "/api/v3/qualitydefinition",
    "customformat": "/api/v3/customformat",
    "importlist": "/api/v3/importlist",
    "metadata": "/api/v3/metadata",
    "tag": "/api/v3/tag",
}

ARR_EDITABLE_RESOURCES_BY_SERVICE = {
    "radarr": ARR_EDITABLE_RESOURCES,
    "prowlarr": {
        "indexer": "/api/v1/indexer",
        "downloadclient": "/api/v1/downloadclient",
        "notification": "/api/v1/notification",
    },
    # Sonarr-only profile resources; Radarr rejects these API routes.
    "sonarr": {
        **ARR_EDITABLE_RESOURCES,
        "languageprofile": "/api/v3/languageprofile",
        "releaseprofile": "/api/v3/releaseprofile",
    },
    "lidarr": {
        "qualityprofile": "/api/v1/qualityprofile",
        "metadataprofile": "/api/v1/metadataprofile",
        "delayprofile": "/api/v1/delayprofile",
        "indexer": "/api/v1/indexer",
        "downloadclient": "/api/v1/downloadclient",
        "notification": "/api/v1/notification",
        "qualitydefinition": "/api/v1/qualitydefinition",
        "customformat": "/api/v1/customformat",
        "importlist": "/api/v1/importlist",
        "metadata": "/api/v1/metadata",
        "tag": "/api/v1/tag",
        "releaseprofile": "/api/v1/releaseprofile",
        "autotagging": "/api/v1/autotagging",
        "remotepathmapping": "/api/v1/remotepathmapping",
    },
}

BAZARR_SETTINGS_FIELDS: dict[str, tuple[str, type]] = {
    "general-use_sonarr": ("Connect to Sonarr", bool),
    "general-use_radarr": ("Connect to Radarr", bool),
    "general-serie_default_enabled": ("Enable defaults for new series", bool),
    "general-serie_default_profile": ("Default series language profile", str),
    "general-movie_default_enabled": ("Enable defaults for new movies", bool),
    "general-movie_default_profile": ("Default movie language profile", str),
    "general-minimum_score": ("Minimum subtitle score for series", int),
    "general-minimum_score_movie": ("Minimum subtitle score for movies", int),
    "general-upgrade_subs": ("Upgrade existing subtitles", bool),
    "general-upgrade_manual": ("Allow manual subtitle upgrades", bool),
    "general-upgrade_frequency": ("Subtitle upgrade interval (hours)", int),
    "general-wanted_search_frequency": ("Series subtitle search interval (hours)", int),
    "general-wanted_search_frequency_movie": ("Movie subtitle search interval (hours)", int),
    "general-use_embedded_subs": ("Use embedded subtitles", bool),
    "general-debug": ("Debug logging", bool),
    "general-concurrent_jobs": ("Maximum concurrent jobs", int),
    "general-page_size": ("Rows per page", int),
    "embeddedsubtitles-fallback_lang": ("Fallback language for embedded subtitles", str),
    "embeddedsubtitles-unknown_as_fallback": ("Use fallback for unknown embedded language", bool),
    "embeddedsubtitles-hi_fallback": ("Use hearing-impaired fallback", bool),
    "embeddedsubtitles-timeout": ("Embedded subtitle probe timeout", int),
    "analytics-enabled": ("Enable anonymous analytics", bool),
}


def _bazarr_settings_values(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise RuntimeError("Bazarr returned an unexpected settings response")
    return {
        key: settings.get(key.split("-", 1)[0], {}).get(key.split("-", 1)[1])
        for key in BAZARR_SETTINGS_FIELDS
        if isinstance(settings.get(key.split("-", 1)[0]), dict)
        and key.split("-", 1)[1] in settings[key.split("-", 1)[0]]
    }


@mcp.tool()
async def bazarr_get_settings() -> dict[str, Any]:
    """Read safe, editable Bazarr settings for the native dashboard form."""
    current = await _arr_request("bazarr", "GET", "/api/system/settings")
    values = _bazarr_settings_values(current)
    return {"fields": [
        {"key": key, "label": BAZARR_SETTINGS_FIELDS[key][0], "value": value}
        for key, value in values.items()
    ]}


@mcp.tool()
async def bazarr_update_settings(settings: dict[str, Any]) -> Any:
    """Update only allowlisted Bazarr system settings (admin permission required)."""
    _require_permission("admin")
    if not isinstance(settings, dict) or not settings:
        raise ValueError("settings must be a non-empty object")
    unknown = set(settings) - set(BAZARR_SETTINGS_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported Bazarr settings: {', '.join(sorted(unknown))}")
    form: dict[str, str] = {}
    for key, value in settings.items():
        _label, expected_type = BAZARR_SETTINGS_FIELDS[key]
        if expected_type is bool:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
            form[key] = "true" if value else "false"
        elif expected_type is int:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{key} must be a non-negative integer")
            form[key] = str(value)
        elif isinstance(value, str):
            form[key] = value[:500]
        else:
            raise ValueError(f"{key} must be a string")
    await _arr_request("bazarr", "POST", "/api/system/settings", form_data=form)
    return {"updated_fields": sorted(settings)}


@mcp.tool()
async def homelabpilot_get_operation_history(limit: int = 100, offset: int = 0) -> Any:
    """Read recent HomeLabPilot writes; stored records contain operation metadata, never request bodies or secrets."""
    return list_audit_events(limit, offset)
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
    """Read editable configuration records from a supported *arr service."""
    resources = ARR_EDITABLE_RESOURCES_BY_SERVICE.get(service)
    if resources is None:
        raise ValueError("service must be radarr, sonarr or prowlarr")
    if resource not in resources:
        raise ValueError(f"resource for {service} must be one of: {', '.join(resources)}")
    result = await _arr_request(service, "GET", resources[resource])
    return _redact_sensitive_config(result)


@mcp.tool()
async def arr_update_configuration(service: str, resource: str, item_id: int, item: dict[str, Any]) -> Any:
    """Update an existing editable configuration record in a supported *arr service."""
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
async def arr_create_configuration(service: str, resource: str, item: dict[str, Any]) -> Any:
    """Create a configuration record in a supported *arr service (admin only)."""
    _require_permission("admin")
    resources = ARR_EDITABLE_RESOURCES_BY_SERVICE.get(service)
    if resources is None:
        raise ValueError("service must be radarr, sonarr or prowlarr")
    if resource not in resources:
        raise ValueError(f"resource for {service} must be one of: {', '.join(resources)}")
    if not isinstance(item, dict) or item.get("id", 0) not in (0, None):
        raise ValueError("new configuration item must be a JSON object with id omitted or set to 0")
    created = await _arr_request(service, "POST", resources[resource], body=item)
    return _redact_sensitive_config(created)


@mcp.tool()
async def arr_preview_delete_configuration(service: str, resource: str, item_id: int) -> Any:
    """Preview an ARR configuration deletion and return its snapshot-bound confirmation token."""
    resources = ARR_EDITABLE_RESOURCES_BY_SERVICE.get(service)
    if resources is None or resource not in resources or item_id < 1:
        raise ValueError("service, resource or item_id is invalid")
    current = await _arr_request(service, "GET", f"{resources[resource]}/{item_id}")
    if not isinstance(current, dict) or int(current.get("id", 0)) != item_id:
        raise RuntimeError(f"{service} returned an unexpected configuration record")
    label = str(current.get("name") or current.get("host") or current.get("path") or f"{resource} #{item_id}")
    return {
        "service": service,
        "resource": resource,
        "id": item_id,
        "label": label,
        "confirmation_text": f"DELETE {service}/{resource}/{item_id}: {label}",
        "preview_token": _preview_token({"service": service, "resource": resource, "id": item_id, "record": current}),
        "summary": _redact_sensitive_config({k: current[k] for k in ("name", "host", "path", "implementation", "enable", "protocol") if k in current}),
    }


@mcp.tool()
async def arr_delete_configuration(
    service: str, resource: str, item_id: int, preview_token: str, typed_confirmation: str
) -> Any:
    """Delete an ARR configuration only after the snapshot and exact preview text are confirmed (admin)."""
    _require_permission("admin")
    resources = ARR_EDITABLE_RESOURCES_BY_SERVICE.get(service)
    if resources is None:
        raise ValueError("service must be radarr, sonarr or prowlarr")
    if resource not in resources:
        raise ValueError(f"resource for {service} must be one of: {', '.join(resources)}")
    if item_id < 1:
        raise ValueError("item_id must be positive")
    if not preview_token.strip() or not typed_confirmation.strip():
        raise ValueError("preview_token and typed_confirmation are required")
    current = await _arr_request(service, "GET", f"{resources[resource]}/{item_id}")
    if not isinstance(current, dict) or int(current.get("id", 0)) != item_id:
        raise RuntimeError(f"{service} returned an unexpected configuration record")
    expected_token = _preview_token({"service": service, "resource": resource, "id": item_id, "record": current})
    if not hmac.compare_digest(expected_token, preview_token):
        raise ValueError("The deletion preview is stale; request a new preview")
    label = str(current.get("name") or current.get("host") or current.get("path") or f"{resource} #{item_id}")
    expected_text = f"DELETE {service}/{resource}/{item_id}: {label}"
    if typed_confirmation != expected_text:
        raise ValueError("typed_confirmation does not exactly match the preview")
    return await _arr_request(service, "DELETE", f"{resources[resource]}/{item_id}")


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


def _validate_qbittorrent_location(location: str) -> str:
    """Validate an absolute Linux path on the qBittorrent host."""
    if not isinstance(location, str):
        raise ValueError("location must be an absolute Linux path")
    location = location.strip()
    path = PurePosixPath(location)
    if (
        not location.startswith("/")
        or location.startswith("//")
        or "\\" in location
        or any(part == ".." for part in location.split("/"))
        or any(ord(char) < 32 for char in location)
        or str(path) != (location.rstrip("/") or "/")
    ):
        raise ValueError("location must be a normalized absolute Linux path without '..'")
    return location.rstrip("/") or "/"


@mcp.tool()
async def qbittorrent_list_categories() -> Any:
    """List qBittorrent categories and their configured save paths."""
    result = await qbittorrent_api_request("GET", "/api/v2/torrents/categories")
    if not isinstance(result, dict):
        raise RuntimeError("qBittorrent returned an unexpected category list")
    return result


@mcp.tool()
async def qbittorrent_preview_update_category_path(category: str, save_path: str) -> Any:
    """Preview changing a qBittorrent category's default save path."""
    category = category.strip()
    save_path = _validate_qbittorrent_location(save_path)
    if not category:
        raise ValueError("category cannot be empty")
    categories = await qbittorrent_list_categories()
    current = categories.get(category)
    if not isinstance(current, dict):
        raise ValueError(f"qBittorrent category does not exist: {category}")
    previous_path = str(current.get("savePath", ""))
    confirmation = f"UPDATE CATEGORY PATH: {category} -> {save_path}"
    snapshot = {
        "category": category,
        "previous_save_path": previous_path,
        "save_path": save_path,
    }
    return {
        **snapshot,
        "confirmation_text": confirmation,
        "preview_token": _preview_token(snapshot),
    }


@mcp.tool()
async def qbittorrent_update_category_path(
    category: str, save_path: str, preview_token: str, typed_confirmation: str
) -> Any:
    """Change a qBittorrent category's save path after a current preview and typed confirmation."""
    _require_permission("admin")
    preview = await qbittorrent_preview_update_category_path(category, save_path)
    if not preview_token.strip() or not hmac.compare_digest(
        preview["preview_token"], preview_token
    ):
        raise ValueError("The category path preview is stale; request a new preview")
    if typed_confirmation != preview["confirmation_text"]:
        raise ValueError("typed_confirmation does not exactly match the preview")
    await qbittorrent_api_request(
        "POST",
        "/api/v2/torrents/editCategory",
        data={"category": preview["category"], "savePath": preview["save_path"]},
    )
    updated = await qbittorrent_list_categories()
    actual = updated.get(preview["category"])
    if not isinstance(actual, dict) or str(actual.get("savePath", "")) != preview["save_path"]:
        raise RuntimeError("qBittorrent did not confirm the category save path change")
    return {
        "category": preview["category"],
        "previous_save_path": preview["previous_save_path"],
        "save_path": preview["save_path"],
    }


def _parse_torrent_hashes(hashes: str) -> list[str]:
    selected = [item.strip().lower() for item in re.split(r"[|,]", hashes) if item.strip()]
    if not selected or any(
        not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", item) for item in selected
    ):
        raise ValueError("hashes must contain one or more valid torrent hashes")
    if len(set(selected)) != len(selected):
        raise ValueError("hashes must not contain duplicates")
    return selected


@mcp.tool()
async def qbittorrent_preview_move_torrents(hashes: str, location: str) -> Any:
    """Preview moving selected torrent data to an absolute path without changing anything."""
    selected = _parse_torrent_hashes(hashes)
    location = _validate_qbittorrent_location(location)
    torrents = await qbittorrent_api_request(
        "GET", "/api/v2/torrents/info", params={"hashes": "|".join(selected)}
    )
    if not isinstance(torrents, list):
        raise RuntimeError("qBittorrent returned an unexpected torrent list")
    by_hash = {
        str(item.get("hash", "")).lower(): item
        for item in torrents
        if isinstance(item, dict)
    }
    if set(by_hash) != set(selected):
        raise ValueError("One or more selected torrent hashes are missing from qBittorrent")
    items = [
        {
            "hash": item_hash,
            "name": str(by_hash[item_hash].get("name", "")),
            "category": str(by_hash[item_hash].get("category", "")),
            "state": str(by_hash[item_hash].get("state", "")),
            "content_path": str(by_hash[item_hash].get("content_path", "")),
            "save_path": str(by_hash[item_hash].get("save_path", "")),
        }
        for item_hash in selected
    ]
    moving = [item for item in items if item["save_path"] != location]
    snapshot = {"items": moving, "location": location}
    confirmation = f"MOVE {len(moving)} TORRENTS TO: {location}"
    return {
        "hashes": [item["hash"] for item in moving],
        "items": [
            {key: value for key, value in item.items() if key != "hash"}
            for item in moving
        ],
        "location": location,
        "already_at_location": len(items) - len(moving),
        "confirmation_text": confirmation,
        "preview_token": _preview_token(snapshot),
    }


@mcp.tool()
async def qbittorrent_move_torrents(
    hashes: str, location: str, preview_token: str, typed_confirmation: str
) -> Any:
    """Move selected torrent data after a fresh snapshot preview and exact typed confirmation."""
    _require_permission("admin")
    preview = await qbittorrent_preview_move_torrents(hashes, location)
    if not preview_token.strip() or not hmac.compare_digest(
        preview["preview_token"], preview_token
    ):
        raise ValueError("The move preview is stale; request a new preview")
    if typed_confirmation != preview["confirmation_text"]:
        raise ValueError("typed_confirmation does not exactly match the preview")
    if preview["items"]:
        await qbittorrent_api_request(
            "POST",
            "/api/v2/torrents/setLocation",
            data={"hashes": "|".join(preview["hashes"]), "location": preview["location"]},
        )
    return {
        "requested": len(preview["items"]),
        "already_at_location": preview["already_at_location"],
        "location": preview["location"],
    }


@mcp.tool()
async def arr_list_library(service: str) -> Any:
    """List the movie, series or artist library in Radarr, Sonarr or Lidarr."""
    paths = {"radarr": "/api/v3/movie", "sonarr": "/api/v3/series", "lidarr": "/api/v1/artist"}
    if service not in paths:
        raise ValueError("service must be radarr, sonarr or lidarr")
    return await _arr_request(service, "GET", paths[service])


@mcp.tool()
async def arr_update_library_item(
    service: str,
    item_id: int,
    monitored: bool | None = None,
    quality_profile_id: int | None = None,
    metadata_profile_id: int | None = None,
) -> Any:
    """Update monitoring and profiles for a movie, series or Lidarr artist."""
    _require_permission("operations")
    if service not in {"radarr", "sonarr", "lidarr"}:
        raise ValueError("service must be radarr, sonarr or lidarr")
    if item_id < 1:
        raise ValueError("item_id must be positive")
    if monitored is None and quality_profile_id is None and metadata_profile_id is None:
        raise ValueError("At least one library field must be provided")
    if quality_profile_id is not None and quality_profile_id < 1:
        raise ValueError("quality_profile_id must be positive")
    if metadata_profile_id is not None and (service != "lidarr" or metadata_profile_id < 1):
        raise ValueError("metadata_profile_id is supported for Lidarr and must be positive")
    endpoint = f"/api/v3/movie/{item_id}" if service == "radarr" else f"/api/v3/series/{item_id}" if service == "sonarr" else f"/api/v1/artist/{item_id}"
    current = await _arr_request(service, "GET", endpoint)
    if not isinstance(current, dict) or int(current.get("id", 0)) != item_id:
        raise RuntimeError(f"{service} returned an unexpected library item")
    updated = dict(current)
    if monitored is not None:
        updated["monitored"] = monitored
    if quality_profile_id is not None:
        updated["qualityProfileId"] = quality_profile_id
    if metadata_profile_id is not None:
        updated["metadataProfileId"] = metadata_profile_id
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
    elif service == "lidarr":
        path = "/api/v1/artist/lookup"
    else:
        raise ValueError("service must be radarr, sonarr or lidarr")
    return await _arr_request(service, "GET", path, params={"term": term.strip()})


@mcp.tool()
async def arr_get_history(service: str, page: int = 1, page_size: int = 50) -> Any:
    """Read recent download, import and upgrade history from Radarr, Sonarr or Lidarr."""
    if service not in {"radarr", "sonarr", "lidarr"}:
        raise ValueError("service must be radarr, sonarr or lidarr")
    if page < 1 or not 1 <= page_size <= 200:
        raise ValueError("page must be >= 1 and page_size between 1 and 200")
    if service == "lidarr":
        path = "/api/v1/history"
        params = {
            "page": page, "pageSize": page_size, "includeArtist": "true",
            "includeAlbum": "true", "includeTrack": "true",
        }
    elif service == "sonarr":
        path = "/api/v3/history"
        params = {
            "page": page, "pageSize": page_size, "includeSeries": "true",
            "includeEpisode": "true",
        }
    else:
        path = "/api/v3/history"
        params = {
            "page": page, "pageSize": page_size, "includeMovie": "true",
        }
    return await _arr_request(service, "GET", path, params=params)


@mcp.tool()
async def arr_get_missing_items(service: str, page: int = 1, page_size: int = 50) -> Any:
    """List monitored missing movies, episodes or albums in Radarr, Sonarr or Lidarr."""
    if service not in {"radarr", "sonarr", "lidarr"}:
        raise ValueError("service must be radarr, sonarr or lidarr")
    if page < 1 or not 1 <= page_size <= 200:
        raise ValueError("page must be >= 1 and page_size between 1 and 200")
    prefix = "/api/v1" if service == "lidarr" else "/api/v3"
    params: dict[str, Any] = {"page": page, "pageSize": page_size, "monitored": "true"}
    if service == "lidarr":
        params["includeArtist"] = "true"
    elif service == "sonarr":
        params["includeSeries"] = "true"
    return await _arr_request(service, "GET", f"{prefix}/wanted/missing", params=params)


@mcp.tool()
async def arr_get_queue(service: str, page: int = 1, page_size: int = 50) -> Any:
    """Inspect the current download/import queue in Radarr, Sonarr or Lidarr."""
    if service not in {"radarr", "sonarr", "lidarr"}:
        raise ValueError("service must be radarr, sonarr or lidarr")
    if page < 1 or page_size < 1 or page_size > 200:
        raise ValueError("page must be >= 1 and page_size between 1 and 200")
    if service == "lidarr":
        return await _arr_request(service, "GET", "/api/v1/queue", params={
            "page": page, "pageSize": page_size, "includeUnknownArtistItems": "true",
            "includeArtist": "true", "includeAlbum": "true",
        })
    return await _arr_request(service, "GET", "/api/v3/queue",
        params={"page": page, "pageSize": page_size, "includeUnknownSeriesItems": "true"})


@mcp.tool()
async def arr_get_setup_options(service: str) -> dict[str, Any]:
    """Get root folders and profiles needed when adding movies, series or artists."""
    if service == "lidarr":
        roots, quality_profiles, metadata_profiles = await asyncio.gather(
            _arr_request(service, "GET", "/api/v1/rootfolder"),
            _arr_request(service, "GET", "/api/v1/qualityprofile"),
            _arr_request(service, "GET", "/api/v1/metadataprofile"),
        )
        return {"root_folders": roots, "quality_profiles": quality_profiles, "metadata_profiles": metadata_profiles}
    if service not in {"radarr", "sonarr"}:
        raise ValueError("service must be radarr, sonarr or lidarr")
    roots, profiles = await asyncio.gather(
        _arr_request(service, "GET", "/api/v3/rootfolder"),
        _arr_request(service, "GET", "/api/v3/qualityprofile"),
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
async def arr_add_artist(
    foreign_artist_id: str, artist_name: str, root_folder_path: str,
    quality_profile_id: int, metadata_profile_id: int,
    monitored: bool = True, search_now: bool = False,
) -> Any:
    """Add a MusicBrainz artist to Lidarr and optionally search for missing albums."""
    _require_permission("operations")
    if not foreign_artist_id.strip() or not artist_name.strip():
        raise ValueError("foreign_artist_id and artist_name are required")
    if not root_folder_path.startswith("/") or quality_profile_id < 1 or metadata_profile_id < 1:
        raise ValueError("root_folder_path must be absolute and profile IDs must be positive")
    return await _arr_request("lidarr", "POST", "/api/v1/artist", body={
        "artistName": artist_name.strip(), "foreignArtistId": foreign_artist_id.strip(),
        "rootFolderPath": root_folder_path, "qualityProfileId": quality_profile_id,
        "metadataProfileId": metadata_profile_id, "monitored": monitored,
        "monitorNewItems": "all",
        "addOptions": {"monitor": "all", "monitored": monitored, "searchForMissingAlbums": search_now},
    })


@mcp.tool()
async def lidarr_list_albums(artist_id: int | None = None) -> Any:
    """List Lidarr albums, optionally restricted to one artist."""
    params: dict[str, Any] = {"includeAllArtistAlbums": "true"}
    if artist_id is not None:
        if artist_id < 1:
            raise ValueError("artist_id must be positive")
        params["artistId"] = artist_id
    return await _arr_request("lidarr", "GET", "/api/v1/album", params=params)


@mcp.tool()
async def lidarr_update_album(album_id: int, monitored: bool) -> Any:
    """Update album monitoring while preserving all other Lidarr album fields."""
    _require_permission("operations")
    if album_id < 1:
        raise ValueError("album_id must be positive")
    endpoint = f"/api/v1/album/{album_id}"
    current = await _arr_request("lidarr", "GET", endpoint)
    if not isinstance(current, dict) or int(current.get("id", 0)) != album_id:
        raise RuntimeError("lidarr returned an unexpected album")
    updated = dict(current)
    updated["monitored"] = monitored
    return await _arr_request("lidarr", "PUT", endpoint, body=updated)


@mcp.tool()
async def lidarr_get_history(page: int = 1, page_size: int = 50) -> Any:
    """Read Lidarr download and import history."""
    if page < 1 or page_size < 1 or page_size > 200:
        raise ValueError("page must be >= 1 and page_size between 1 and 200")
    return await _arr_request("lidarr", "GET", "/api/v1/history", params={
        "page": page, "pageSize": page_size, "includeArtist": "true",
        "includeAlbum": "true", "includeTrack": "true",
    })


@mcp.tool()
async def lidarr_get_missing_albums(page: int = 1, page_size: int = 50) -> Any:
    """List monitored albums missing from the Lidarr library."""
    if page < 1 or page_size < 1 or page_size > 200:
        raise ValueError("page must be >= 1 and page_size between 1 and 200")
    return await _arr_request("lidarr", "GET", "/api/v1/wanted/missing", params={
        "page": page, "pageSize": page_size, "includeArtist": "true", "monitored": "true",
    })


@mcp.tool()
async def arr_search_releases(service: str, item_id: int) -> Any:
    """Search available releases for a movie, series or Lidarr album."""
    if item_id < 1:
        raise ValueError("item_id must be positive")
    if service == "radarr":
        return await _arr_request("radarr", "GET", "/api/v3/release", params={"movieId": item_id})
    if service == "sonarr":
        return await _arr_request("sonarr", "GET", "/api/v3/release", params={"seriesId": item_id})
    if service == "lidarr":
        return await _arr_request("lidarr", "GET", "/api/v1/release", params={"albumId": item_id})
    raise ValueError("service must be radarr, sonarr or lidarr")


@mcp.tool()
async def arr_grab_release(service: str, guid: str, indexer_id: int) -> Any:
    """Send a selected release to the configured download client through an *arr service."""
    _require_permission("operations")
    if service not in {"radarr", "sonarr", "lidarr"}:
        raise ValueError("service must be radarr, sonarr or lidarr")
    if not guid.strip() or indexer_id < 1:
        raise ValueError("guid and positive indexer_id are required")
    prefix = "/api/v1" if service == "lidarr" else "/api/v3"
    return await _arr_request(service, "POST", f"{prefix}/release", body={"guid": guid, "indexerId": indexer_id})


@mcp.tool()
async def scryer_introspect() -> Any:
    """Discover Scryer's live GraphQL query and mutation fields and their arguments."""
    query = """
    query HomeLabPilotSchema {
      __schema {
        queryType { name fields { name description args { name type { kind name ofType { kind name ofType { kind name } } } } } }
        mutationType { name fields { name description args { name type { kind name ofType { kind name ofType { kind name } } } } } }
      }
    }
    """
    return await scryer_graphql(query)


@mcp.tool()
async def scryer_list_recycled_items(limit: int = 100, offset: int = 0) -> Any:
    """Read Scryer's recycle-bin settings and a page of recycled media files."""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    query = """
    query HomeLabPilotRecycleBin($limit: Int!, $offset: Int!) {
      recycleBinSettings {
        enabled path retentionDays effectivePaths validationError
      }
      recycledItems(limit: $limit, offset: $offset) {
        totalCount
        items {
          id originalPath fileName sizeBytes titleId titleName titleFacet episodeId
          reason recycledAt scheduledDeletionAt mediaRoot libraryId libraryName
        }
      }
    }
    """
    return await scryer_graphql(query, {"limit": limit, "offset": offset})


@mcp.tool()
async def scryer_list_titles(
    search: str = "", facet: str | None = None, library_id: str | None = None,
    limit: int = 50, offset: int = 0,
) -> Any:
    """Search Scryer's permission-filtered title catalog with bounded pagination."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("limit must be 1..100 and offset must be non-negative")
    query = """
    query HomeLabPilotTitles($query: String, $facet: MediaFacetValue, $libraryIds: [ID!], $limit: Int, $offset: Int) {
      titles(query: $query, facet: $facet, libraryIds: $libraryIds, limit: $limit, offset: $offset) {
        totalCount hasMore managedBytes
        items {
          id libraryId libraryName name facet monitored year contentStatus language
          runtimeMinutes qualityProfileId rootFolderPath sizeBytes mediaResolution mediaHdr
          episodesOwned episodesMonitored episodesTotal
        }
      }
    }
    """
    variables: dict[str, Any] = {"query": search.strip() or None, "facet": facet, "limit": limit, "offset": offset}
    variables["libraryIds"] = [library_id] if library_id else None
    return await _scryer_request(query, variables)


@mcp.tool()
async def scryer_list_media_requests(facet: str | None = None, status: str | None = None) -> Any:
    """List Scryer media requests visible to the configured Scryer account."""
    query = """
    query HomeLabPilotRequests($facet: MediaFacetValue, $status: MediaRequestStatusValue) {
      mediaRequests(facet: $facet, status: $status) {
        id title year facet status createdAt updatedAt createdTitleId
        requestedQualityProfileName approvedQualityProfileName requestedLeaseDays approvedLeaseDays
      }
    }
    """
    return await _scryer_request(query, {"facet": facet, "status": status})


@mcp.tool()
async def scryer_list_audit_events(
    limit: int = 100, title_id: str | None = None, facet: str | None = None,
    after_sequence: int | None = None, before_sequence: int | None = None,
) -> Any:
    """Read Scryer's audit trail without returning event payloads that may contain extra metadata."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    query = """
    query HomeLabPilotScryerAudit($limit: Int!, $titleId: ID, $facet: MediaFacetValue, $afterSequence: Long, $beforeSequence: Long) {
      auditLog(limit: $limit, titleId: $titleId, facet: $facet, afterSequence: $afterSequence, beforeSequence: $beforeSequence) {
        sequence eventId occurredAt actorKind actorUserId actorDisplayName titleId facet eventType streamKind streamId
      }
    }
    """
    return await _scryer_request(query, {
        "limit": limit, "titleId": title_id, "facet": facet,
        "afterSequence": after_sequence, "beforeSequence": before_sequence,
    })


@mcp.tool()
async def scryer_preview_delete_title(title_id: str) -> Any:
    """Preview all file, subtitle, image and directory effects of deleting one Scryer title."""
    if not title_id.strip():
        raise ValueError("title_id is required")
    query = """
    query HomeLabPilotDeleteTitlePreview($titleId: ID!) {
      deleteTitlePreview(titleId: $titleId) {
        fingerprint totalFileCount mediaCount subtitleCount imageCount otherCount directoryCount
        requiresTypedConfirmation typedConfirmationPrompt targetLabel samplePaths
      }
    }
    """
    return await _scryer_request(query, {"titleId": title_id})


@mcp.tool()
async def scryer_delete_title(
    title_id: str, preview_fingerprint: str, typed_confirmation: str,
    delete_files_on_disk: bool = False,
) -> Any:
    """Delete a Scryer title only when its preview fingerprint and typed title confirmation still match."""
    _require_permission("admin")
    if not title_id.strip() or not preview_fingerprint.strip() or not typed_confirmation.strip():
        raise ValueError("title_id, preview_fingerprint and typed_confirmation are required")
    preview = await scryer_preview_delete_title(title_id)
    if not isinstance(preview, dict) or preview.get("errors"):
        raise RuntimeError("Scryer could not produce a valid deletion preview")
    details = (preview.get("data") or {}).get("deleteTitlePreview") or {}
    if details.get("fingerprint") != preview_fingerprint:
        raise ValueError("The deletion preview is stale; request a new preview before confirming")
    expected = details.get("typedConfirmationPrompt") or details.get("targetLabel")
    if not expected or typed_confirmation != expected:
        raise ValueError("typed_confirmation must exactly match the preview's confirmation prompt or title")
    query = """
    mutation HomeLabPilotDeleteTitle($input: DeleteTitleInput!) {
      deleteTitle(input: $input) {
        id recyclePurged recyclePreserved recycleBusy recycleFailed
      }
    }
    """
    return await _scryer_request(query, {"input": {
        "titleId": title_id,
        "deleteFilesOnDisk": delete_files_on_disk,
        "previewFingerprint": preview_fingerprint,
        "typedConfirmation": typed_confirmation,
    }}, allow_destructive=True)


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
async def qbittorrent_preview_delete_torrents(hashes: str, delete_files: bool = False) -> Any:
    """Preview exactly which torrents will be removed and whether their data files will be deleted."""
    selected = [item.strip().lower() for item in re.split(r"[|,]", hashes) if item.strip()]
    if not selected or any(not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", item) for item in selected):
        raise ValueError("hashes must contain one or more valid torrent hashes")
    torrents = await qbittorrent_api_request(
        "GET", "/api/v2/torrents/info", params={"hashes": "|".join(selected)}
    )
    if not isinstance(torrents, list):
        raise RuntimeError("qBittorrent returned an unexpected torrent list")
    by_hash = {str(item.get("hash", "")).lower(): item for item in torrents if isinstance(item, dict)}
    if set(by_hash) != set(selected):
        raise ValueError("One or more selected torrent hashes are missing from qBittorrent")
    items = [{
        "hash": key, "name": str(by_hash[key].get("name", "")),
        "size": int(by_hash[key].get("size", 0)),
        "category": str(by_hash[key].get("category", "")),
        "state": str(by_hash[key].get("state", "")),
        "save_path": str(by_hash[key].get("save_path", "")),
    } for key in selected]
    summary = f"TORRENT: {items[0]['name']}" if len(items) == 1 else f"{len(items)} TORRENTS"
    confirmation = f"DELETE FILES: {summary}" if delete_files else f"DELETE {summary}"
    snapshot = {"items": items, "delete_files": delete_files}
    return {
        "items": [{key: value for key, value in item.items() if key != "hash"} for item in items],
        "delete_files": delete_files,
        "confirmation_text": confirmation,
        "preview_token": _preview_token(snapshot),
    }


@mcp.tool()
async def qbittorrent_delete_torrents(
    hashes: str, preview_token: str, typed_confirmation: str, delete_files: bool = False
) -> Any:
    """Remove torrents only after a fresh snapshot preview and exact typed confirmation (admin)."""
    _require_permission("admin")
    preview = await qbittorrent_preview_delete_torrents(hashes, delete_files)
    if not preview_token.strip() or not hmac.compare_digest(preview["preview_token"], preview_token):
        raise ValueError("The deletion preview is stale; request a new preview")
    if typed_confirmation != preview["confirmation_text"]:
        raise ValueError("typed_confirmation does not exactly match the preview")
    selected = [item.strip().lower() for item in re.split(r"[|,]", hashes) if item.strip()]
    return await qbittorrent_api_request(
        "POST", "/api/v2/torrents/delete",
        data={"hashes": "|".join(selected), "deleteFiles": str(delete_files).lower()},
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


def _require_docker_permission(required: str = "read") -> None:
    if os.getenv("HOMELABPILOT_DOCKER_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("Optional Docker management is disabled")
    levels = {"read": 0, "operations": 1}
    configured = os.getenv("HOMELABPILOT_DOCKER_PERMISSION_LEVEL", "read").strip().lower()
    if configured not in levels:
        raise RuntimeError("HOMELABPILOT_DOCKER_PERMISSION_LEVEL must be read or operations")
    if levels[configured] < levels[required]:
        raise PermissionError(f"Docker action requires separate '{required}' Docker permission")


async def _docker_gateway_request(method: str, path: str) -> Any:
    token = os.getenv("HOMELABPILOT_DOCKER_GATEWAY_TOKEN", "").strip()
    if len(token) < 32:
        raise ValueError("HOMELABPILOT_DOCKER_GATEWAY_TOKEN must contain at least 32 characters")
    base = _base_url("HOMELABPILOT_DOCKER_GATEWAY_URL")
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        response = await client.request(
            method, urljoin(base + "/", path.lstrip("/")),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        response.raise_for_status()
        return _decode_response(response)


@mcp.tool()
async def docker_list_allowlisted_containers() -> Any:
    """List only containers explicitly allowlisted in the optional restricted Docker gateway."""
    _require_docker_permission("read")
    return await _docker_gateway_request("GET", "/v1/containers")


def _docker_action_snapshot(container: str, action: str) -> dict[str, str]:
    """Validate and normalize a restricted Docker action before preview or execution."""
    name = container.strip()
    if not name or len(name) > 128 or "/" in name or ".." in name or any(ord(ch) < 32 for ch in name):
        raise ValueError("container must be a valid allowlisted name or ID (1-128 characters)")
    if action not in {"start", "stop", "restart"}:
        raise ValueError("action must be start, stop or restart")
    return {"service": "docker", "container": name, "action": action}


@mcp.tool()
async def docker_preview_container_action(container: str, action: str) -> dict[str, str]:
    """Preview starting, stopping or restarting one allowlisted container."""
    _require_docker_permission("operations")
    snapshot = _docker_action_snapshot(container, action)
    phrase = f"CONFIRM DOCKER {action.upper()} {snapshot['container']}"
    return {
        "preview_token": _preview_token(snapshot),
        "typed_confirmation": phrase,
        "container": snapshot["container"],
        "action": action,
        "warning": "This changes container state. stop/restart can interrupt services and active tasks.",
    }


@mcp.tool()
async def docker_control_allowlisted_container(
    container: str, action: str, preview_token: str = "", typed_confirmation: str = ""
) -> Any:
    """Execute only a matching previewed Docker action after exact typed confirmation."""
    _require_docker_permission("operations")
    snapshot = _docker_action_snapshot(container, action)
    expected_token = _preview_token(snapshot)
    expected_phrase = f"CONFIRM DOCKER {action.upper()} {snapshot['container']}"
    if not hmac.compare_digest(preview_token, expected_token):
        raise PermissionError("The Docker action preview is missing, stale or does not match")
    if not hmac.compare_digest(typed_confirmation, expected_phrase):
        raise PermissionError(f"Type exactly: {expected_phrase}")
    try:
        result = await _docker_gateway_request(
            "POST", f"/v1/containers/{quote(snapshot['container'], safe='')}/{action}"
        )
    except Exception:
        _audit(action, "docker", snapshot["container"], outcome="failed")
        raise
    _audit(action, "docker", snapshot["container"])
    return result


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


async def _web_api_request_inner(
    path: str, method: str, query: dict[str, list[str]], payload: dict[str, Any]
) -> Any:
    """Shared browser API actions; all service calls reuse the same configured API layer."""
    if method == "GET" and path == "/web-api/apps/config":
        return get_app_config()
    if method == "POST" and path == "/web-api/apps/config":
        app_id = str(payload.get("app_id", ""))
        values = payload.get("values", {})
        clear_secrets = payload.get("clear_secrets", [])
        result = save_app_config(app_id, values, clear_secrets)
        _audit("CONFIG_UPDATE", app_id, ",".join(sorted(values)))
        return result

    if method == "GET" and path == "/web-api/tdarr/status":
        return await integration_status.dashboard_read("tdarr", "status")
    if method == "GET" and path == "/web-api/tdarr/nodes":
        return await integration_status.dashboard_read("tdarr", "nodes")
    if method == "GET" and path == "/web-api/tdarr/jobs":
        start = int((query.get("start") or ["0"])[0])
        page_size = int((query.get("page_size") or ["25"])[0])
        file_path_contains = (query.get("file_path_contains") or [""])[0]
        return await integration_status.dashboard_read(
            "tdarr", "job_reports", start=start, page_size=page_size,
            file_path_contains=file_path_contains,
        )
    if method == "GET" and path == "/web-api/tdarr/files":
        search_term = (query.get("search_term") or [""])[0]
        greater_than_gb = float((query.get("greater_than_gb") or ["0"])[0])
        less_than_gb = float((query.get("less_than_gb") or ["0"])[0])
        return await integration_status.dashboard_read(
            "tdarr", "search_files", search_term=search_term,
            greater_than_gb=greater_than_gb, less_than_gb=less_than_gb,
        )
    if method == "GET" and path == "/web-api/tdarr/job-report":
        job_id = (query.get("id") or [""])[0]
        if not job_id:
            raise ValueError("A Tdarr job ID is required")
        return await integration_status.dashboard_read("tdarr", "job_report", job_id=job_id)

    if method == "POST" and path == "/web-api/scryer/graphql":
        query_text = str(payload.get("query", ""))
        if not query_text.strip():
            raise ValueError("GraphQL query cannot be empty")
        variables = payload.get("variables", {})
        if not isinstance(variables, dict):
            raise ValueError("GraphQL variables must be a JSON object")
        return await scryer_graphql(query_text, variables)

    if method == "GET" and path == "/web-api/audit":
        limit = int((query.get("limit") or ["100"])[0])
        offset = int((query.get("offset") or ["0"])[0])
        return list_audit_events(limit, offset)

    if method == "GET" and path == "/web-api/bazarr/settings":
        return await bazarr_get_settings()
    if method == "POST" and path == "/web-api/bazarr/settings":
        settings = payload.get("settings", {})
        return await bazarr_update_settings(settings)

    if method == "GET" and path == "/web-api/docker/containers":
        return await docker_list_allowlisted_containers()
    if method == "POST" and path == "/web-api/docker/control":
        return await docker_control_allowlisted_container(
            str(payload.get("container", "")), str(payload.get("action", ""))
        )

    if method == "GET" and path == "/web-api/scryer/recycle-bin":
        limit = int((query.get("limit") or ["100"])[0])
        offset = int((query.get("offset") or ["0"])[0])
        return await scryer_list_recycled_items(limit, offset)

    if method == "GET" and path == "/web-api/scryer/titles":
        return await scryer_list_titles(
            search=(query.get("search") or [""])[0],
            facet=(query.get("facet") or [""])[0] or None,
            library_id=(query.get("library_id") or [""])[0] or None,
            limit=int((query.get("limit") or ["50"])[0]),
            offset=int((query.get("offset") or ["0"])[0]),
        )
    if method == "GET" and path == "/web-api/scryer/requests":
        return await scryer_list_media_requests(
            facet=(query.get("facet") or [""])[0] or None,
            status=(query.get("status") or [""])[0] or None,
        )
    if method == "GET" and path == "/web-api/scryer/audit":
        return await scryer_list_audit_events(
            limit=int((query.get("limit") or ["100"])[0]),
            title_id=(query.get("title_id") or [""])[0] or None,
            facet=(query.get("facet") or [""])[0] or None,
            after_sequence=int((query.get("after_sequence") or [""])[0]) if (query.get("after_sequence") or [""])[0] else None,
            before_sequence=int((query.get("before_sequence") or [""])[0]) if (query.get("before_sequence") or [""])[0] else None,
        )
    if method == "POST" and path == "/web-api/scryer/delete-title/preview":
        return await scryer_preview_delete_title(str(payload.get("title_id", "")))
    if method == "POST" and path == "/web-api/scryer/delete-title":
        return await scryer_delete_title(
            str(payload.get("title_id", "")),
            str(payload.get("preview_fingerprint", "")),
            str(payload.get("typed_confirmation", "")),
            bool(payload.get("delete_files_on_disk", False)),
        )

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
        if service == "lidarr":
            return await arr_add_artist(
                str(payload.get("foreign_artist_id", "")), str(payload.get("artist_name", "")),
                str(payload.get("root_folder_path", "")), int(payload.get("quality_profile_id", 0)),
                int(payload.get("metadata_profile_id", 0)), monitored=monitored, search_now=search_now,
            )
        raise ValueError("service must be radarr, sonarr or lidarr")

    if method == "POST" and path == "/web-api/api":
        service = str(payload.get("service", ""))
        api_method = str(payload.get("method", "GET")).upper()
        api_path = str(payload.get("path", ""))
        params = payload.get("params", {})
        body = payload.get("body")
        if service not in {"radarr", "sonarr", "prowlarr", "bazarr", "lidarr"}:
            raise ValueError("service must be radarr, sonarr, prowlarr, bazarr or lidarr")
        if api_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("method must be GET, POST, PUT, PATCH or DELETE")
        if not isinstance(params, dict):
            raise ValueError("params must be a JSON object")
        return await arr_api_request(service, api_method, api_path, params=params, body=body)

    if method == "GET" and path == "/web-api/settings":
        service = (query.get("service") or [""])[0]
        resource = (query.get("resource") or [""])[0]
        if service == "qbittorrent":
            return await qbittorrent_get_preferences()
        return await arr_get_configuration(service, resource)
    if method == "POST" and path == "/web-api/settings/create":
        return await arr_create_configuration(
            str(payload.get("service", "")),
            str(payload.get("resource", "")),
            payload.get("item", {}),
        )
    if method == "POST" and path == "/web-api/settings/preview-delete":
        return await arr_preview_delete_configuration(
            str(payload.get("service", "")), str(payload.get("resource", "")),
            int(payload.get("id", 0)),
        )
    if method == "POST" and path == "/web-api/settings/delete":
        return await arr_delete_configuration(
            str(payload.get("service", "")),
            str(payload.get("resource", "")),
            int(payload.get("id", 0)),
            str(payload.get("preview_token", "")),
            str(payload.get("typed_confirmation", "")),
        )
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
        metadata_profile_id = payload.get("metadata_profile_id")
        return await arr_update_library_item(
            service, item_id, monitored=monitored,
            quality_profile_id=int(profile_id) if profile_id is not None else None,
            metadata_profile_id=int(metadata_profile_id) if metadata_profile_id is not None else None,
        )
    if method == "GET" and path == "/web-api/albums":
        artist_id_text = (query.get("artist_id") or [""])[0]
        return await lidarr_list_albums(int(artist_id_text) if artist_id_text else None)
    if method == "POST" and path == "/web-api/albums/update":
        monitored = payload.get("monitored")
        if not isinstance(monitored, bool):
            raise ValueError("monitored must be a boolean")
        return await lidarr_update_album(int(payload.get("id", 0)), monitored)
    if method == "GET" and path == "/web-api/history":
        if (query.get("service") or [""])[0] != "lidarr":
            raise ValueError("history is currently supported for lidarr")
        return await lidarr_get_history()
    if method == "GET" and path == "/web-api/missing":
        if (query.get("service") or [""])[0] != "lidarr":
            raise ValueError("missing albums are currently supported for lidarr")
        return await lidarr_get_missing_albums()
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
    if method == "POST" and path == "/web-api/torrents/category":
        hashes = str(payload.get("hashes", ""))
        category = str(payload.get("category", ""))
        return await qbittorrent_set_category(hashes, category)
    if method == "POST" and path == "/web-api/torrents/delete-preview":
        hashes = str(payload.get("hashes", ""))
        delete_files = payload.get("delete_files", False)
        if not isinstance(delete_files, bool):
            raise ValueError("delete_files must be a boolean")
        return await qbittorrent_preview_delete_torrents(hashes, delete_files)
    if method == "POST" and path == "/web-api/torrents/delete":
        hashes = str(payload.get("hashes", ""))
        delete_files = payload.get("delete_files", False)
        if not isinstance(delete_files, bool):
            raise ValueError("delete_files must be a boolean")
        return await qbittorrent_delete_torrents(
            hashes, str(payload.get("preview_token", "")),
            str(payload.get("typed_confirmation", "")), delete_files,
        )
    if path.startswith("/web-api/agents/"):
        gateway_url = os.getenv("HOMELABPILOT_AGENT_GATEWAY_URL", "http://homelabpilot-agents:8766").rstrip("/")
        headers = {"Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, read=5.0)) as client:
                if method == "GET" and path == "/web-api/agents/status":
                    response = await client.get(f"{gateway_url}/health", headers=headers)
                elif method == "GET" and path == "/web-api/agents/conversations":
                    agent = (query.get("agent") or ["codex"])[0]
                    if agent != "codex":
                        raise ValueError("Unknown agent")
                    response = await client.get(f"{gateway_url}/conversations", headers=headers, params={"agent": agent})
                elif method == "GET" and path == "/web-api/agents/conversation":
                    conversation_id = (query.get("id") or [""])[0]
                    if not re.fullmatch(r"[0-9a-f-]{36}", conversation_id):
                        raise ValueError("A valid conversation id is required")
                    response = await client.get(f"{gateway_url}/conversations/{conversation_id}", headers=headers)
                elif method == "POST" and path == "/web-api/agents/chat":
                    prompt = str(payload.get("prompt", "")).strip()
                    if not prompt or len(prompt) > 20000:
                        raise ValueError("The message must contain between 1 and 20,000 characters")
                    agent = str(payload.get("agent", "codex"))
                    if agent != "codex":
                        raise ValueError("Unknown agent")
                    body = {"prompt": prompt, "agent": agent}
                    if payload.get("conversation_id"):
                        body["conversation_id"] = str(payload["conversation_id"])
                    response = await client.post(f"{gateway_url}/chat", headers=headers, json=body)
                elif method == "GET" and path == "/web-api/agents/job":
                    job_id = (query.get("id") or [""])[0]
                    if not re.fullmatch(r"[0-9a-f-]{36}", job_id):
                        raise ValueError("A valid job id is required")
                    response = await client.get(f"{gateway_url}/jobs/{job_id}", headers=headers)
                else:
                    raise ValueError("Unknown agent gateway operation")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("error", "Agent gateway request failed")
            except ValueError:
                detail = "Agent gateway request failed"
            raise ValueError(detail) from exc
        except httpx.RequestError as exc:
            raise ValueError("Agent gateway is unavailable; check the homelabpilot-agents container") from exc

    raise ValueError("Unknown HomeLabPilot web API operation")


async def _web_api_request(
    path: str, method: str, query: dict[str, list[str]], payload: dict[str, Any]
) -> Any:
    source_token = _AUDIT_SOURCE.set("web")
    try:
        return await _web_api_request_inner(path, method, query, payload)
    finally:
        _AUDIT_SOURCE.reset(source_token)


def main() -> None:
    """Run HomeLabPilot over stdio (default) or authenticated Streamable HTTP."""
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
    web_username = os.getenv("HOMELABPILOT_WEB_USERNAME", "admin").strip() or "admin"
    web_password = os.getenv("HOMELABPILOT_WEB_PASSWORD", "").strip() or token
    app = HomeLabPilotWebMiddleware(
        app, token, stack_status, _web_api_request,
        web_username=web_username, web_password=web_password,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

