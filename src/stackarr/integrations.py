"""Native API integrations for the broader HomeLabPilot app catalog.

Hosts and credentials are read only from operator configuration. Generic writes
are admin-only and require a signed request preview plus an exact typed phrase.
"""
from __future__ import annotations

import asyncio
import hmac
import os
from typing import Any
from urllib.parse import urljoin

import httpx


HTTP_INTEGRATIONS = {
    "plex": ("PLEX_URL", "PLEX_TOKEN", "plex", "/identity"),
    "jellyfin": ("JELLYFIN_URL", "JELLYFIN_API_KEY", "emby", "/System/Info/Public"),
    "seerr": ("SEERR_URL", "SEERR_API_KEY", "x-api-key", "/api/v1/status"),
    "transmission": ("TRANSMISSION_URL", "", "basic", "/transmission/rpc"),
    "pulsarr": ("PULSARR_URL", "PULSARR_API_KEY", "bearer", "/api/docs"),
    "cleanuparr": ("CLEANUPARR_URL", "CLEANUPARR_API_KEY", "x-api-key", "/"),
    "maintainerr": ("MAINTAINERR_URL", "", "none", "/"),
    "agregarr": ("AGREGARR_URL", "AGREGARR_API_KEY", "x-api-key", "/"),
    "tracearr": ("TRACEARR_URL", "TRACEARR_API_KEY", "x-api-key", "/"),
    "immich": ("IMMICH_URL", "IMMICH_API_KEY", "x-api-key", "/api/server/ping"),
    "romm": ("ROMM_URL", "ROMM_API_TOKEN", "bearer", "/api/platforms"),
    "bookorbit": ("BOOKORBIT_URL", "BOOKORBIT_API_KEY", "x-api-key", "/"),
    "tinymediamanager": ("TINYMEDIAMANAGER_URL", "TINYMEDIAMANAGER_API_KEY", "x-api-key", "/"),
    "tidarr": ("TIDARR_URL", "TIDARR_API_KEY", "x-api-key", "/"),
    "flaresolverr": ("FLARESOLVERR_URL", "", "none", "/"),
    "cloudflare": ("CLOUDFLARE_API_URL", "CLOUDFLARE_API_TOKEN", "bearer", "/user/tokens/verify"),
}
NON_HTTP_INTEGRATIONS = {
    "recyclarr": ("RECYCLARR_CONTAINER", None, "container/CLI"),
    "postgres": ("POSTGRES_HOST", "POSTGRES_PORT", "TCP reachability"),
    "redis": ("REDIS_HOST", "REDIS_PORT", "TCP reachability"),
    "docker": ("STACKARR_DOCKER_ENABLED", None, "restricted Docker gateway"),
}
TRANSMISSION_READ_METHODS = {"session-get", "session-stats", "torrent-get"}


def _is_configured(service: str, config: tuple[str, str, str, str]) -> bool:
    url_env, credential_env, _, _ = config
    if not os.getenv(url_env, "").strip():
        return False
    return not credential_env or bool(os.getenv(credential_env, "").strip())




def register_integration_tools(
    *,
    mcp: Any,
    require_permission: Any,
    make_make_preview_token: Any,
    safe_path: Any,
    base_url: Any,
    decode_response: Any,
    audit: Any,
    timeout: float,
) -> Any:
    """Register MCP tools and return a status-check coroutine for stack_status."""

    def resolve(service: str) -> tuple[str, str, str, str]:
        if service not in HTTP_INTEGRATIONS:
            raise ValueError(
                f"Unsupported HTTP integration '{service}'. Choose: {', '.join(HTTP_INTEGRATIONS)}"
            )
        url_env, credential_env, auth_mode, health_path = HTTP_INTEGRATIONS[service]
        root = base_url(url_env)
        credential = os.getenv(credential_env, "").strip() if credential_env else ""
        if credential_env and not credential:
            raise ValueError(f"Missing configuration: {credential_env}")
        return root, credential, auth_mode, health_path

    def endpoint(service: str, path: str) -> str:
        root, _, _, _ = resolve(service)
        checked = safe_path(path)
        if service == "transmission":
            if checked not in {"/", "/transmission/rpc"}:
                raise ValueError("Transmission uses only the configured RPC endpoint")
            return root
        return urljoin(root + "/", checked.lstrip("/"))

    def headers_for(credential: str, mode: str) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if not credential:
            return headers
        if mode == "emby":
            headers["X-Emby-Token"] = credential
        elif mode == "x-api-key":
            headers["X-Api-Key"] = credential
        elif mode == "bearer":
            headers["Authorization"] = f"Bearer {credential}"
        return headers

    async def request(
        service: str,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> Any:
        root, credential, mode, _ = resolve(service)
        verb = method.upper()
        if verb not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("method must be GET, POST, PUT, PATCH or DELETE")
        url = endpoint(service, path)
        headers = headers_for(credential, mode)
        query = dict(params or {})
        if mode == "plex" and credential:
            query["X-Plex-Token"] = credential
        auth = None
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                if service == "transmission":
                    if verb != "POST":
                        raise ValueError("Transmission RPC calls use POST")
                    username = os.getenv("TRANSMISSION_USERNAME", "").strip()
                    password = os.getenv("TRANSMISSION_PASSWORD", "").strip()
                    if username or password:
                        if not username or not password:
                            raise ValueError("Set both TRANSMISSION_USERNAME and TRANSMISSION_PASSWORD")
                        auth = (username, password)
                    response = await client.post(url, json=body, auth=auth, headers=headers)
                    if response.status_code == 409:
                        session_id = response.headers.get("X-Transmission-Session-Id")
                        if session_id:
                            headers["X-Transmission-Session-Id"] = session_id
                            response = await client.post(url, json=body, auth=auth, headers=headers)
                else:
                    response = await client.request(
                        verb, url, params=query, json=body, headers=headers, auth=auth
                    )
                response.raise_for_status()
                output = decode_response(response)
        except Exception:
            is_read_only = verb == "GET" or (
                service == "transmission"
                and isinstance(body, dict)
                and body.get("method") in TRANSMISSION_READ_METHODS
            )
            if not is_read_only:
                audit(verb, service, path, "failed")
            raise RuntimeError(
                f"{service} API request failed; verify the URL, credentials, path and service logs"
            ) from None
        is_read_only = verb == "GET" or (
            service == "transmission"
            and isinstance(body, dict)
            and body.get("method") in TRANSMISSION_READ_METHODS
        )
        if not is_read_only:
            audit(verb, service, path)
        return output

    @mcp.tool()
    async def integration_catalog() -> dict[str, Any]:
        """List additional integrations and setup modes without returning credentials."""
        services = {
            "radarr": {"configured": bool(os.getenv("RADARR_URL", "").strip()), "mode": "ARR REST"},
            "sonarr": {"configured": bool(os.getenv("SONARR_URL", "").strip()), "mode": "ARR REST"},
            "lidarr": {"configured": bool(os.getenv("LIDARR_URL", "").strip()), "mode": "ARR REST"},
            "prowlarr": {"configured": bool(os.getenv("PROWLARR_URL", "").strip()), "mode": "ARR REST"},
            "bazarr": {"configured": bool(os.getenv("BAZARR_URL", "").strip()), "mode": "ARR REST"},
            "scryer": {"configured": bool(os.getenv("SCRYER_URL", "").strip()), "mode": "GraphQL"},
            "qbittorrent": {"configured": bool(os.getenv("QBITTORRENT_URL", "").strip()), "mode": "Web API"},
        }
        services.update({
            service: {
                "configured": _is_configured(service, config),
                "mode": "native HTTP API",
            }
            for service, config in HTTP_INTEGRATIONS.items()
        })
        services.update({
            "recyclarr": {
                "configured": bool(os.getenv("RECYCLARR_CONTAINER", "").strip()),
                "mode": "container/CLI",
            },
            "postgres": {
                "configured": bool(os.getenv("POSTGRES_HOST", "").strip()),
                "mode": "TCP reachability",
            },
            "redis": {
                "configured": bool(os.getenv("REDIS_HOST", "").strip()),
                "mode": "TCP reachability",
            },
            "docker": {
                "configured": os.getenv("STACKARR_DOCKER_ENABLED", "false").lower()
                in {"1", "true", "yes", "on"},
                "mode": "restricted Docker gateway",
            },
        })
        return {"integrations": services}

    @mcp.tool()
    async def integration_api_request(
        service: str,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> Any:
        """Read a configured native HTTP API; targets and credentials stay server-side."""
        verb = method.upper()
        if service == "transmission":
            rpc_method = body.get("method", "") if isinstance(body, dict) else ""
            if verb != "POST" or rpc_method not in TRANSMISSION_READ_METHODS:
                raise PermissionError(
                    "Transmission reads must use session-get, session-stats or torrent-get"
                )
            return await request(service, verb, path, params, body)
        if verb != "GET":
            raise PermissionError("This tool is read-only; preview non-GET requests first")
        return await request(service, verb, path, params, body)

    @mcp.tool()
    async def integration_preview_api_write(
        service: str,
        method: str,
        path: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Prepare an admin-only native API write and return its signed preview and phrase."""
        require_permission("admin")
        verb = method.upper()
        if verb == "GET":
            raise ValueError("GET requests do not need a write preview")
        endpoint(service, path)
        if (
            service == "transmission"
            and isinstance(body, dict)
            and body.get("method") in TRANSMISSION_READ_METHODS
        ):
            raise ValueError("Use integration_api_request for read-only Transmission RPC calls")
        snapshot = {
            "service": service,
            "method": verb,
            "path": path,
            "params": params or {},
            "body": body,
        }
        phrase = f"CONFIRM {service} {verb} {path}"
        return {"preview_token": make_preview_token(snapshot), "typed_confirmation": phrase}

    @mcp.tool()
    async def integration_confirm_api_write(
        service: str,
        method: str,
        path: str,
        preview_token_value: str,
        typed_confirmation: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Apply a previewed native API write after exact typed confirmation."""
        require_permission("admin")
        verb = method.upper()
        if verb == "GET":
            raise ValueError("GET requests are read-only")
        endpoint(service, path)
        snapshot = {
            "service": service,
            "method": verb,
            "path": path,
            "params": params or {},
            "body": body,
        }
        expected_token = make_preview_token(snapshot)
        expected_phrase = f"CONFIRM {service} {verb} {path}"
        if not hmac.compare_digest(preview_token_value, expected_token):
            raise PermissionError("The API write preview is stale or does not match this request")
        if not hmac.compare_digest(typed_confirmation, expected_phrase):
            raise PermissionError(f"Type exactly: {expected_phrase}")
        if service == "transmission" and verb != "POST":
            raise ValueError("Transmission RPC writes must use POST")
        return await request(service, verb, path, params, body)

    async def status_checks() -> dict[str, Any]:
        checks: dict[str, Any] = {}
        for service, config in HTTP_INTEGRATIONS.items():
            url_env, _, _, health_path = config
            if not _is_configured(service, config):
                checks[service] = {"configured": False}
                continue
            try:
                if service == "transmission":
                    result = await request(
                        service,
                        "POST",
                        health_path,
                        body={"method": "session-get", "arguments": {}},
                    )
                else:
                    result = await request(service, "GET", health_path)
                checks[service] = {"configured": True, "ok": True}
            except Exception:
                checks[service] = {
                    "configured": True,
                    "ok": False,
                    "error": f"{service} API check failed; verify its URL, credential and health endpoint",
                }
        for service, (host_env, port_env, mode) in NON_HTTP_INTEGRATIONS.items():
            if service == "docker":
                checks[service] = {
                    "configured": os.getenv(host_env, "false").lower()
                    in {"1", "true", "yes", "on"},
                    "mode": mode,
                }
                continue
            host = os.getenv(host_env, "").strip()
            if not host:
                checks[service] = {"configured": False, "mode": mode}
                continue
            if service == "recyclarr":
                checks[service] = {"configured": True, "mode": mode}
                continue
            port: int | None = None
            try:
                port = int(os.getenv(port_env or "", "5432" if service == "postgres" else "6379"))
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=timeout
                )
                writer.close()
                await writer.wait_closed()
                checks[service] = {
                    "configured": True,
                    "ok": True,
                    "host": host,
                    "port": port,
                    "mode": mode,
                }
            except Exception as exc:
                checks[service] = {
                    "configured": True,
                    "ok": False,
                    "host": host,
                    "port": port,
                    "mode": mode,
                    "error": "TCP check failed; verify host, port and service availability",
                }
        return checks

    return status_checks
