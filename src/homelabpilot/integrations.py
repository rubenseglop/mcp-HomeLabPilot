"""Native API integrations for the broader HomeLabPilot app catalog.

Hosts and credentials are read only from operator configuration. Generic writes
are admin-only and require a signed request preview plus an exact typed phrase.
"""
from __future__ import annotations

import asyncio
import hmac
import os
from typing import Any
from urllib.parse import quote, urljoin

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
    "tracearr": ("TRACEARR_URL", "TRACEARR_API_KEY", "bearer", "/"),
    "immich": ("IMMICH_URL", "IMMICH_API_KEY", "x-api-key", "/api/server/ping"),
    "homeassistant": ("HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN", "bearer", "/api/"),
    "romm": ("ROMM_URL", "ROMM_API_TOKEN", "bearer", "/api/platforms"),
    "bookorbit": ("BOOKORBIT_URL", "BOOKORBIT_API_KEY", "x-api-key", "/"),
    "tinymediamanager": ("TINYMEDIAMANAGER_URL", "TINYMEDIAMANAGER_API_KEY", "api-key", "/"),
    "tidarr": ("TIDARR_URL", "TIDARR_API_KEY", "x-api-key", "/"),
    "flaresolverr": ("FLARESOLVERR_URL", "", "none", "/"),
    "cloudflare": ("CLOUDFLARE_API_URL", "CLOUDFLARE_API_TOKEN", "bearer", "/user/tokens/verify"),
}
NON_HTTP_INTEGRATIONS = {
    "recyclarr": ("RECYCLARR_CONTAINER", None, "container/CLI"),
    "postgres": ("POSTGRES_HOST", "POSTGRES_PORT", "TCP reachability"),
    "redis": ("REDIS_HOST", "REDIS_PORT", "TCP reachability"),
    "docker": ("HOMELABPILOT_DOCKER_ENABLED", None, "restricted Docker gateway"),
}
TRANSMISSION_READ_METHODS = {"session-get", "session-stats", "torrent-get"}


def _is_configured(config: tuple[str, str, str, str]) -> bool:
    url_env, credential_env, _, _ = config
    if not os.getenv(url_env, "").strip():
        return False
    return not credential_env or bool(os.getenv(credential_env, "").strip())




def register_integration_tools(
    *,
    mcp: Any,
    require_permission: Any,
    make_preview_token: Any,
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
        elif mode == "api-key":
            headers["api-key"] = credential
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
        _, credential, mode, _ = resolve(service)
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
                "configured": _is_configured(config),
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
                "configured": os.getenv("HOMELABPILOT_DOCKER_ENABLED", "false").lower()
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
        preview_token: str,
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
        if not hmac.compare_digest(preview_token, expected_token):
            raise PermissionError("The API write preview is stale or does not match this request")
        if not hmac.compare_digest(typed_confirmation, expected_phrase):
            raise PermissionError(f"Type exactly: {expected_phrase}")
        if service == "transmission" and verb != "POST":
            raise ValueError("Transmission RPC writes must use POST")
        return await request(service, verb, path, params, body)


    # Service-specific read workflows. These keep the supported API paths fixed
    # and provide useful MCP tools without exposing arbitrary host selection.
    @mcp.tool()
    async def plex_get_library_sections() -> Any:
        """List Plex library sections using the configured Plex server and token."""
        return await request("plex", "GET", "/library/sections")

    @mcp.tool()
    async def plex_get_recently_added(section_id: int, limit: int = 25) -> Any:
        """List recently added Plex items from one library section."""
        if section_id < 1 or not 1 <= limit <= 100:
            raise ValueError("section_id must be positive and limit must be between 1 and 100")
        return await request(
            "plex", "GET", f"/library/sections/{section_id}/recentlyAdded",
            params={"X-Plex-Container-Start": 0, "X-Plex-Container-Size": limit},
        )

    @mcp.tool()
    async def transmission_get_session() -> Any:
        """Read Transmission session configuration and daemon information."""
        return await request(
            "transmission", "POST", "/transmission/rpc",
            body={"method": "session-get", "arguments": {}},
        )

    @mcp.tool()
    async def transmission_get_statistics() -> Any:
        """Read Transmission transfer totals and current speeds."""
        return await request(
            "transmission", "POST", "/transmission/rpc",
            body={"method": "session-stats", "arguments": {}},
        )

    @mcp.tool()
    async def transmission_list_torrents(
        fields: list[str] | None = None, ids: list[int] | None = None
    ) -> Any:
        """List Transmission torrents with selected fields; defaults to a useful status summary."""
        selected = fields or [
            "id", "name", "status", "percentDone", "rateDownload", "rateUpload",
            "eta", "totalSize", "downloadDir", "error", "errorString",
        ]
        allowed = {
            "id", "name", "status", "percentDone", "rateDownload", "rateUpload",
            "eta", "totalSize", "downloadDir", "error", "errorString", "addedDate",
            "doneDate", "uploadedEver", "downloadedEver", "ratio", "peersConnected",
            "peersGettingFromUs", "peersSendingToUs", "files", "fileStats", "trackers",
        }
        if not selected or len(selected) > 40 or set(selected) - allowed:
            raise ValueError(f"fields must be selected from: {', '.join(sorted(allowed))}")
        if ids is not None and (not ids or len(ids) > 200 or any(i < 1 for i in ids)):
            raise ValueError("ids must contain 1..200 positive torrent IDs")
        args: dict[str, Any] = {"fields": selected}
        if ids is not None:
            args["ids"] = ids
        return await request(
            "transmission", "POST", "/transmission/rpc",
            body={"method": "torrent-get", "arguments": args},
        )

    @mcp.tool()
    async def plex_get_active_sessions() -> Any:
        """Show current Plex playback sessions, including client and stream details."""
        return await request("plex", "GET", "/status/sessions")

    @mcp.tool()
    async def plex_get_on_deck() -> Any:
        """List in-progress and next-up Plex library items."""
        return await request("plex", "GET", "/library/onDeck")

    @mcp.tool()
    async def plex_get_recently_added_all() -> Any:
        """List recently added Plex items across all libraries."""
        return await request("plex", "GET", "/library/recentlyAdded")

    @mcp.tool()
    async def jellyfin_get_libraries() -> Any:
        """List Jellyfin virtual folders/libraries."""
        return await request("jellyfin", "GET", "/Library/VirtualFolders")

    @mcp.tool()
    async def jellyfin_get_active_sessions() -> Any:
        """List current Jellyfin playback sessions and their transcoding/direct-play state."""
        return await request("jellyfin", "GET", "/Sessions")

    @mcp.tool()
    async def jellyfin_get_server_info() -> Any:
        """Read Jellyfin server name, version and operating-system details."""
        return await request("jellyfin", "GET", "/System/Info")

    @mcp.tool()
    async def jellyfin_search_items(search_term: str, limit: int = 25) -> Any:
        """Search the Jellyfin library by title."""
        term = search_term.strip()
        if not term or len(term) > 200 or not 1 <= limit <= 100:
            raise ValueError("search_term is required (max 200 chars) and limit must be 1..100")
        return await request(
            "jellyfin", "GET", "/Items",
            params={"searchTerm": term, "Limit": limit, "Recursive": "true"},
        )

    @mcp.tool()
    async def seerr_get_requests(
        media_type: str = "all", status_filter: str = "all", take: int = 20, skip: int = 0
    ) -> Any:
        """List Seerr requests; media_type is all/movie/tv and status_filter is a request status."""
        allowed_statuses = {
            "all", "approved", "available", "pending", "processing",
            "unavailable", "failed", "deleted", "completed",
        }
        if media_type not in {"all", "movie", "tv"}:
            raise ValueError("media_type must be all, movie or tv")
        if status_filter not in allowed_statuses:
            raise ValueError(f"status_filter must be one of: {', '.join(sorted(allowed_statuses))}")
        if not 1 <= take <= 100 or skip < 0:
            raise ValueError("take must be 1..100 and skip must be non-negative")
        return await request(
            "seerr", "GET", "/api/v1/request",
            params={"take": take, "skip": skip, "filter": status_filter, "mediaType": media_type},
        )

    @mcp.tool()
    async def seerr_get_status() -> Any:
        """Read Seerr application status and version information."""
        return await request("seerr", "GET", "/api/v1/status")

    @mcp.tool()
    async def seerr_get_application_data_status() -> Any:
        """Read Seerr application-data volume status."""
        return await request("seerr", "GET", "/api/v1/status/appdata")

    @mcp.tool()
    async def seerr_search_media(search_term: str) -> Any:
        """Search movies and TV metadata through Seerr."""
        term = search_term.strip()
        if not term or len(term) > 200:
            raise ValueError("search_term is required and must be at most 200 characters")
        return await request("seerr", "GET", "/api/v1/search", params={"query": term})

    @mcp.tool()
    async def homeassistant_get_config() -> Any:
        """Read Home Assistant core configuration, version, timezone and loaded components."""
        return await request("homeassistant", "GET", "/api/config")

    @mcp.tool()
    async def homeassistant_list_states(domain: str = "", limit: int = 500) -> Any:
        """List current Home Assistant entity states, optionally filtered by domain."""
        if not 1 <= limit <= 2000:
            raise ValueError("limit must be between 1 and 2000")
        params: dict[str, Any] = {}
        if domain:
            import re
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", domain):
                raise ValueError("domain must be a valid Home Assistant domain")
        states = await request("homeassistant", "GET", "/api/states", params=params)
        if not isinstance(states, list):
            raise RuntimeError("Home Assistant returned an unexpected states response")
        if domain:
            states = [item for item in states if isinstance(item, dict) and str(item.get("entity_id", "")).startswith(domain + ".")]
        return {"total": len(states), "returned": min(len(states), limit), "states": states[:limit]}

    @mcp.tool()
    async def homeassistant_get_state(entity_id: str) -> Any:
        """Read the current state and attributes for one Home Assistant entity."""
        import re
        if not re.fullmatch(r"[a-z_][a-z0-9_]*\\.[a-z0-9_]+", entity_id):
            raise ValueError("entity_id must use the domain.entity_id format")
        return await request("homeassistant", "GET", f"/api/states/{entity_id}")

    @mcp.tool()
    async def homeassistant_get_history(
        entity_id: str, start_time: str, end_time: str = "",
        minimal_response: bool = True, no_attributes: bool = False,
    ) -> Any:
        """Read historical state changes for one Home Assistant entity over a time range."""
        import re
        from datetime import datetime
        if not re.fullmatch(r"[a-z_][a-z0-9_]*\\.[a-z0-9_]+", entity_id):
            raise ValueError("entity_id must use the domain.entity_id format")
        def validate_timestamp(value: str, label: str) -> None:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                raise ValueError(f"{label} must be an ISO-8601 timestamp") from None
            if parsed.tzinfo is None:
                raise ValueError(f"{label} must include a timezone")
        validate_timestamp(start_time, "start_time")
        params: dict[str, Any] = {
            "filter_entity_id": entity_id,
            "minimal_response": str(minimal_response).lower(),
            "no_attributes": str(no_attributes).lower(),
        }
        if end_time:
            validate_timestamp(end_time, "end_time")
            params["end_time"] = end_time
        return await request(
            "homeassistant", "GET",
            "/api/history/period/" + quote(start_time, safe=""),
            params=params,
        )

    @mcp.tool()
    async def homeassistant_list_services() -> Any:
        """List Home Assistant service domains and available service names without invoking them."""
        return await request("homeassistant", "GET", "/api/services")

    @mcp.tool()
    async def cloudflare_list_zones(page: int = 1, per_page: int = 50, name: str = "") -> Any:
        """List Cloudflare zones visible to the configured API token."""
        if page < 1 or not 1 <= per_page <= 100:
            raise ValueError("page must be >= 1 and per_page must be 1..100")
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if name.strip():
            params["name"] = name.strip()[:253]
        return await request("cloudflare", "GET", "/zones", params=params)

    @mcp.tool()
    async def cloudflare_list_dns_records(
        zone_id: str, page: int = 1, per_page: int = 100,
        record_type: str = "", name: str = "",
    ) -> Any:
        """List DNS records in a Cloudflare zone; optional type/name filters are supported."""
        import re
        if not re.fullmatch(r"[A-Fa-f0-9]{32}", zone_id):
            raise ValueError("zone_id must be a 32-character Cloudflare zone ID")
        if page < 1 or not 1 <= per_page <= 100:
            raise ValueError("page must be >= 1 and per_page must be 1..100")
        allowed_types = {"A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"}
        if record_type and record_type.upper() not in allowed_types:
            raise ValueError(f"record_type must be one of: {', '.join(sorted(allowed_types))}")
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if record_type:
            params["type"] = record_type.upper()
        if name.strip():
            params["name"] = name.strip()[:253]
        return await request(
            "cloudflare", "GET", f"/zones/{zone_id}/dns_records", params=params
        )

    @mcp.tool()
    async def immich_get_albums() -> Any:
        """List Immich albums."""
        return await request("immich", "GET", "/api/albums")

    @mcp.tool()
    async def immich_search_assets(search_term: str, page: int = 1, size: int = 25) -> Any:
        """Search Immich photos and videos by metadata using its native metadata-search API."""
        term = search_term.strip()
        if not term or len(term) > 200 or page < 1 or not 1 <= size <= 100:
            raise ValueError("search_term is required (max 200 chars), page >= 1 and size 1..100")
        return await request(
            "immich", "POST", "/api/search/metadata",
            body={"query": term, "page": page, "size": size},
        )

    @mcp.tool()
    async def immich_get_server_statistics() -> Any:
        """Read Immich server statistics."""
        return await request("immich", "GET", "/api/server/statistics")

    @mcp.tool()
    async def romm_get_platforms() -> Any:
        """List platforms configured in RomM."""
        return await request("romm", "GET", "/api/platforms")

    @mcp.tool()
    async def romm_search_roms(search_term: str, limit: int = 25, offset: int = 0) -> Any:
        """Search the RomM game library with bounded pagination."""
        term = search_term.strip()
        if len(term) < 2 or len(term) > 200 or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("search_term must be 2..200 chars, limit 1..100 and offset non-negative")
        return await request(
            "romm", "GET", "/api/roms",
            params={"search_term": term, "limit": limit, "offset": offset},
        )

    @mcp.tool()
    async def romm_list_roms(limit: int = 50, offset: int = 0, platform_ids: list[int] | None = None) -> Any:
        """List RomM library entries, optionally restricted to platform IDs."""
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be non-negative")
        if platform_ids is not None and (
            not platform_ids or len(platform_ids) > 50 or any(value < 1 for value in platform_ids)
        ):
            raise ValueError("platform_ids must contain 1..50 positive IDs")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if platform_ids:
            params["platform_ids"] = platform_ids
        return await request("romm", "GET", "/api/roms", params=params)

    @mcp.tool()
    async def romm_get_rom(rom_id: int) -> Any:
        """Read the metadata and availability details for one RomM game."""
        if rom_id < 1:
            raise ValueError("rom_id must be positive")
        return await request("romm", "GET", f"/api/roms/{rom_id}")

    @mcp.tool()
    async def romm_list_collections() -> Any:
        """List RomM game collections."""
        return await request("romm", "GET", "/api/collections")

    async def status_checks() -> dict[str, Any]:
        checks: dict[str, Any] = {}
        for service, config in HTTP_INTEGRATIONS.items():
            url_env, _, _, health_path = config
            if not _is_configured(config):
                continue
            try:
                if service == "transmission":
                    await request(
                        service,
                        "POST",
                        health_path,
                        body={"method": "session-get", "arguments": {}},
                    )
                else:
                    await request(service, "GET", health_path)
                checks[service] = {"configured": True, "ok": True}
            except Exception:
                checks[service] = {
                    "configured": True,
                    "ok": False,
                    "error": f"{service} API check failed; verify its URL, credential and health endpoint",
                }
        for service, (host_env, port_env, mode) in NON_HTTP_INTEGRATIONS.items():
            if service in {"docker", "recyclarr"}:
                continue
            host = os.getenv(host_env, "").strip()
            if not host:
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
