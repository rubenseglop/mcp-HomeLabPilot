"""Native API integrations for the broader HomeLabPilot app catalog.

Hosts and credentials are read only from operator configuration. Generic writes
are admin-only and require a signed request preview plus an exact typed phrase.
"""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import os
import secrets
from typing import Any
from urllib.parse import quote, urljoin

import httpx


HTTP_INTEGRATIONS = {
    "questarr": ("QUESTARR_URL", "QUESTARR_API_KEY", "x-api-key", "/api/integration/ping"),
    "frigate": ("FRIGATE_URL", "FRIGATE_API_TOKEN", "bearer", "/api/stats"),
    "seanime": ("SEANIME_URL", "SEANIME_PASSWORD", "seanime-token", "/api/v1/status"),
    "plex": ("PLEX_URL", "PLEX_TOKEN", "plex", "/identity"),
    "jellyfin": ("JELLYFIN_URL", "JELLYFIN_API_KEY", "emby", "/System/Info/Public"),
    "seerr": ("SEERR_URL", "SEERR_API_KEY", "x-api-key", "/api/v1/status"),
    "transmission": ("TRANSMISSION_URL", "", "basic", "/transmission/rpc"),
    "pulsarr": ("PULSARR_URL", "PULSARR_API_KEY", "x-api-key", "/health"),
    "cleanuparr": ("CLEANUPARR_URL", "CLEANUPARR_API_KEY", "x-api-key", "/health"),
    "maintainerr": ("MAINTAINERR_URL", "", "none", "/api/health/ready"),
    "agregarr": ("AGREGARR_URL", "AGREGARR_API_KEY", "x-api-key", "/api/v1/status"),
    "tracearr": ("TRACEARR_URL", "TRACEARR_API_KEY", "bearer", "/api/v1/public/health"),
    "tdarr": ("TDARR_URL", "", "x-api-key", "/api/v2/status"),
    "immich": ("IMMICH_URL", "IMMICH_API_KEY", "x-api-key", "/api/server/ping"),
    "homeassistant": ("HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN", "bearer", "/api/"),
    "romm": ("ROMM_URL", "ROMM_API_TOKEN", "bearer", "/api/platforms"),
    "bookorbit": ("BOOKORBIT_URL", "BOOKORBIT_API_KEY", "x-api-key", "/api/v1/health"),
    "tinymediamanager": ("TINYMEDIAMANAGER_URL", "TINYMEDIAMANAGER_API_KEY", "api-key", "/api/system"),
    "tidarr": ("TIDARR_URL", "TIDARR_API_KEY", "x-api-key", "/api/is-auth-active"),
    "flaresolverr": ("FLARESOLVERR_URL", "", "none", "/"),
    "youtarr": ("YOUTARR_URL", "YOUTARR_API_KEY", "x-api-key", "/external-api/v1/capabilities"),
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
        if service == "tdarr":
            credential = os.getenv("TDARR_API_KEY", "").strip()
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
        if mode == "seanime-token":
            import hashlib
            headers["X-Seanime-Token"] = hashlib.sha256(credential.encode("utf-8")).hexdigest()
        elif mode == "emby":
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
        read_only_post: bool = False,
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
            is_read_only = verb == "GET" or read_only_post or (
                service == "transmission"
                and isinstance(body, dict)
                and body.get("method") in TRANSMISSION_READ_METHODS
            )
            if not is_read_only:
                audit(verb, service, path, "failed")
            raise RuntimeError(
                f"{service} API request failed; verify the URL, credentials, path and service logs"
            ) from None
        is_read_only = verb == "GET" or read_only_post or (
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
            "seanime": {"configured": bool(os.getenv("SEANIME_URL", "").strip()), "mode": "native API"},
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
        if service == "questarr" and path not in {"/api/integration/ping", "/api/integration/library"}:
            raise PermissionError("Questarr generic reads are restricted to its read-scoped integration API")
        if service == "frigate" and path not in {"/api/stats", "/api/events", "/api/review", "/api/review/summary", "/api/profile"}:
            raise PermissionError("Frigate generic reads are restricted to approved status/event endpoints")
        if service == "seanime":
            allowed = {"/api/v1/status", "/api/v1/library/collection",
                       "/api/v1/anilist/collection", "/api/v1/anilist/collection/raw",
                       "/api/v1/library/local-files"}
            if path not in allowed and not path.startswith("/api/v1/library/anime-entry/"):
                raise PermissionError("Seanime generic reads are restricted to known read-only status/library endpoints")
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



    # Questarr and Frigate read-only integrations.
    @mcp.tool()
    async def questarr_get_status() -> Any:
        """Read Questarr integration ping, version and API-key scope."""
        return await request("questarr", "GET", "/api/integration/ping")

    @mcp.tool()
    async def questarr_get_library(
        status: str = "", include_hidden: bool = False, limit: int = 100
    ) -> Any:
        """Read Questarr's game library using a read-scoped integration API key."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if len(status) > 200:
            raise ValueError("status filter must be at most 200 characters")
        params: dict[str, Any] = {"includeHidden": str(include_hidden).lower()}
        if status.strip():
            params["status"] = status.strip()
        result = await request("questarr", "GET", "/api/integration/library", params=params)
        if isinstance(result, dict) and isinstance(result.get("games"), list):
            result["returned"] = min(len(result["games"]), limit)
            result["games"] = result["games"][:limit]
        return result

    @mcp.tool()
    async def frigate_get_status() -> Any:
        """Read Frigate NVR statistics, camera/detector state and system metrics."""
        return await request("frigate", "GET", "/api/stats")

    @mcp.tool()
    async def frigate_list_events(
        limit: int = 50, offset: int = 0, camera: str = "all",
        label: str = "all", after: str | None = None, before: str | None = None,
    ) -> Any:
        """List Frigate detection events with bounded pagination and optional filters."""
        if not 1 <= limit <= 200 or offset < 0 or offset > 100000:
            raise ValueError("limit must be 1..200 and offset must be 0..100000")
        if len(camera) > 100 or len(label) > 100:
            raise ValueError("camera and label filters must be at most 100 characters")
        params: dict[str, Any] = {
            "limit": limit, "offset": offset, "camera": camera, "label": label,
            "include_thumbnails": 0,
        }
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        return await request("frigate", "GET", "/api/events", params=params)

    @mcp.tool()
    async def frigate_list_review_items(
        limit: int = 50, camera: str = "all", label: str = "all",
        severity: str | None = None,
    ) -> Any:
        """List Frigate review items (alerts/detections) for operator triage."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if len(camera) > 100 or len(label) > 100:
            raise ValueError("camera and label filters must be at most 100 characters")
        if severity not in {None, "alert", "detection"}:
            raise ValueError("severity must be alert, detection or omitted")
        params: dict[str, Any] = {"limit": limit, "cameras": camera, "labels": label}
        if severity:
            params["severity"] = severity
        return await request("frigate", "GET", "/api/review", params=params)

    @mcp.tool()
    async def frigate_get_review_summary(
        camera: str = "all", label: str = "all", timezone: str = "utc"
    ) -> Any:
        """Read Frigate review counters for the last 24 hours and historical days."""
        if len(camera) > 100 or len(label) > 100 or len(timezone) > 64:
            raise ValueError("camera/label must be <=100 characters and timezone <=64")
        return await request(
            "frigate", "GET", "/api/review/summary",
            params={"cameras": camera, "labels": label, "timezone": timezone},
        )

    # Tdarr workflows. POST query endpoints are explicitly marked read-only so
    # they are not misclassified as mutations in the operation audit.
    def _tdarr_id(value: str, label: str = "file_id") -> str:
        item = value.strip()
        if not item or len(item) > 2048 or any(ord(ch) < 32 for ch in item):
            raise ValueError(f"{label} is required and must be a valid Tdarr identifier/path")
        return item

    @mcp.tool()
    async def tdarr_get_status() -> Any:
        """Read Tdarr server status/version. Requires TDARR_URL and optionally TDARR_API_KEY."""
        return await request("tdarr", "GET", "/api/v2/status")

    @mcp.tool()
    async def tdarr_get_nodes() -> Any:
        """List connected Tdarr nodes and their worker/resource information."""
        return await request("tdarr", "GET", "/api/v2/get-nodes")

    @mcp.tool()
    async def tdarr_search_files(
        search_term: str = "",
        greater_than_gb: float = 0,
        less_than_gb: float = 0,
    ) -> Any:
        """Search Tdarr's file database by filename/path substring and optional size bounds (GB)."""
        term = search_term.strip()
        if len(term) > 300:
            raise ValueError("search_term must be at most 300 characters")
        if greater_than_gb < 0 or less_than_gb < 0:
            raise ValueError("File-size bounds cannot be negative")
        if greater_than_gb and less_than_gb and greater_than_gb >= less_than_gb:
            raise ValueError("greater_than_gb must be smaller than less_than_gb")
        return await request(
            "tdarr", "POST", "/api/v2/search-db",
            body={"data": {"string": term, "greaterThanGB": greater_than_gb, "lessThanGB": less_than_gb}},
            read_only_post=True,
        )

    @mcp.tool()
    async def tdarr_list_job_reports(
        start: int = 0, page_size: int = 25, file_path_contains: str = ""
    ) -> Any:
        """List recent Tdarr job reports, optionally filtering by a media path substring."""
        if start < 0 or not 1 <= page_size <= 100:
            raise ValueError("start must be non-negative and page_size must be 1..100")
        filters = [{"id": "file", "value": file_path_contains.strip()}] if file_path_contains.strip() else []
        return await request(
            "tdarr", "POST", "/api/v2/client/jobs",
            body={"data": {
                "start": start, "pageSize": page_size, "filters": filters,
                "sorts": [{"id": "start", "desc": True}], "opts": {},
            }},
            read_only_post=True,
        )

    @mcp.tool()
    async def tdarr_get_job_report(job_id: str) -> Any:
        """Read a Tdarr job report, including its FFmpeg/HandBrake log text."""
        identifier = _tdarr_id(job_id, "job_id")
        return await request("tdarr", "GET", f"/api/v2/job-reports/{quote(identifier, safe='')}")

    @mcp.tool()
    async def tdarr_preview_requeue_files(file_ids: list[str]) -> dict[str, Any]:
        """Preview requeueing selected Tdarr files through their existing library flow; does not transcode yet."""
        require_permission("operations")
        ids = list(dict.fromkeys(_tdarr_id(value) for value in file_ids))
        if not ids or len(ids) > 50:
            raise ValueError("Select between 1 and 50 individual files; library-wide requeues are intentionally not exposed")
        snapshot = {
            "service": "tdarr", "operation": "requeue-files",
            "file_ids": ids, "updates": {"TranscodeDecisionMaker": "Queued"},
        }
        phrase = f"CONFIRM TDARR REQUEUE {len(ids)} FILES"
        return {
            "preview_token": make_preview_token(snapshot),
            "typed_confirmation": phrase,
            "files_to_requeue": ids,
            "effect": "Tdarr volverá a evaluar estos archivos con el flujo/stack configurado en su biblioteca. El worker podrá sustituir el original según la configuración de Tdarr.",
        }

    @mcp.tool()
    async def tdarr_confirm_requeue_files(
        file_ids: list[str], preview_token: str, typed_confirmation: str
    ) -> Any:
        """Requeue only the exact files in a valid preview after exact typed confirmation."""
        require_permission("operations")
        ids = list(dict.fromkeys(_tdarr_id(value) for value in file_ids))
        if not ids or len(ids) > 50:
            raise ValueError("Select between 1 and 50 individual files")
        snapshot = {
            "service": "tdarr", "operation": "requeue-files",
            "file_ids": ids, "updates": {"TranscodeDecisionMaker": "Queued"},
        }
        expected_phrase = f"CONFIRM TDARR REQUEUE {len(ids)} FILES"
        if not hmac.compare_digest(preview_token, make_preview_token(snapshot)):
            raise PermissionError("The Tdarr preview is stale or does not match these file IDs")
        if not hmac.compare_digest(typed_confirmation, expected_phrase):
            raise PermissionError(f"Type exactly: {expected_phrase}")
        return await request(
            "tdarr", "POST", "/api/v2/bulk-update-files",
            body={"data": {"fileIds": ids, "updatedObj": {"TranscodeDecisionMaker": "Queued"}}},
        )

    @mcp.tool()
    async def tdarr_preview_rescan_file(file_id: str, library_id: str) -> dict[str, str]:
        """Preview a metadata/queue rescan for one file; this does not delete or transcode media."""
        require_permission("operations")
        identifier = _tdarr_id(file_id)
        library = _tdarr_id(library_id, "library_id")
        snapshot = {"service": "tdarr", "operation": "rescan-file", "file_id": identifier, "library_id": library}
        phrase = "CONFIRM TDARR RESCAN FILE"
        return {"preview_token": make_preview_token(snapshot), "typed_confirmation": phrase}

    @mcp.tool()
    async def tdarr_confirm_rescan_file(
        file_id: str, library_id: str, preview_token: str, typed_confirmation: str
    ) -> Any:
        """Run the single-file Tdarr rescan after its preview is confirmed."""
        require_permission("operations")
        identifier = _tdarr_id(file_id)
        library = _tdarr_id(library_id, "library_id")
        snapshot = {"service": "tdarr", "operation": "rescan-file", "file_id": identifier, "library_id": library}
        if not hmac.compare_digest(preview_token, make_preview_token(snapshot)):
            raise PermissionError("The Tdarr rescan preview is stale or does not match this file")
        if not hmac.compare_digest(typed_confirmation, "CONFIRM TDARR RESCAN FILE"):
            raise PermissionError("Type exactly: CONFIRM TDARR RESCAN FILE")
        return await request(
            "tdarr", "POST", "/api/v2/rescan-file",
            body={"data": {"_id": identifier, "DB": library}},
        )

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
    async def pulsarr_get_health() -> Any:
        """Read Pulsarr health and database connectivity status."""
        return await request("pulsarr", "GET", "/health")

    @mcp.tool()
    async def pulsarr_get_approval_requests(limit: int = 25, offset: int = 0) -> Any:
        """List Pulsarr requests waiting for approval, with bounded pagination."""
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be non-negative")
        return await request(
            "pulsarr", "GET", "/v1/approval/requests",
            params={"limit": limit, "offset": offset},
        )

    @mcp.tool()
    async def pulsarr_list_content_router_rules() -> Any:
        """List Pulsarr content-router rules and their routing conditions."""
        return await request("pulsarr", "GET", "/v1/content-router/rules")

    @mcp.tool()
    async def youtarr_get_capabilities() -> Any:
        """Read Youtarr external API version, enabled features, key scopes and quota limits."""
        return await request("youtarr", "GET", "/external-api/v1/capabilities")

    @mcp.tool()
    async def youtarr_list_channels(
        page_size: int = 50, cursor: str = "", search: str = "",
        subfolder: str = "", sort_by: str = "title", sort_order: str = "asc",
    ) -> Any:
        """List channels granted to the configured Youtarr external API key."""
        if not 1 <= page_size <= 100 or sort_by not in {"title", "videoCount", "downloadedCount", "id"} or sort_order not in {"asc", "desc"}:
            raise ValueError("page_size must be 1..100; sort_by/sort_order must use documented values")
        params: dict[str, Any] = {"pageSize": page_size, "sortBy": sort_by, "sortOrder": sort_order}
        for key, value, max_len in (("cursor", cursor, 2000), ("search", search, 200), ("subfolder", subfolder, 255)):
            if value:
                if len(value) > max_len:
                    raise ValueError(f"{key} is too long")
                params[key] = value
        return await request("youtarr", "GET", "/external-api/v1/channels", params=params)

    @mcp.tool()
    async def youtarr_list_videos(
        page_size: int = 50, cursor: str = "", search: str = "",
        status: str = "all", tab_type: str = "videos",
        sort_by: str = "date", sort_order: str = "desc",
    ) -> Any:
        """List policy-filtered YouTube video catalog entries available to the configured key."""
        if not 1 <= page_size <= 100 or status not in {"all", "requestable", "available", "downloaded", "requested"}:
            raise ValueError("page_size must be 1..100 and status must be a documented value")
        if tab_type not in {"videos", "shorts", "streams"} or sort_by not in {"date", "title", "duration"} or sort_order not in {"asc", "desc"}:
            raise ValueError("tab_type, sort_by or sort_order is invalid")
        params: dict[str, Any] = {"pageSize": page_size, "status": status, "tabType": tab_type, "sortBy": sort_by, "sortOrder": sort_order}
        if cursor:
            if len(cursor) > 2000:
                raise ValueError("cursor is too long")
            params["cursor"] = cursor
        if search:
            if len(search) > 200:
                raise ValueError("search is too long")
            params["search"] = search
        return await request("youtarr", "GET", "/external-api/v1/videos", params=params)

    @mcp.tool()
    async def youtarr_get_video(youtube_id: str) -> Any:
        """Read cached metadata and request/download status for one policy-visible YouTube video."""
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_id):
            raise ValueError("youtube_id must be an 11-character YouTube video ID")
        return await request("youtarr", "GET", f"/external-api/v1/videos/{youtube_id}")

    @mcp.tool()
    async def youtarr_list_requests(page_size: int = 50, cursor: str = "", status: str = "") -> Any:
        """List requests owned by the configured Youtarr API key."""
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be 1..100")
        if status and status not in {"pending", "approved", "processing", "completed", "rejected", "failed", "cancelled"}:
            raise ValueError("status is not a documented request status")
        params: dict[str, Any] = {"pageSize": page_size}
        if cursor:
            if len(cursor) > 2000:
                raise ValueError("cursor is too long")
            params["cursor"] = cursor
        if status:
            params["status"] = status
        return await request("youtarr", "GET", "/external-api/v1/requests", params=params)

    @mcp.tool()
    async def youtarr_get_request(request_id: int) -> Any:
        """Read one request owned by the configured Youtarr API key."""
        if request_id < 1:
            raise ValueError("request_id must be positive")
        return await request("youtarr", "GET", f"/external-api/v1/requests/{request_id}")

    def _youtarr_request_payload(
        request_type: str, youtube_id: str = "", channel_id: int = 0, channel_url: str = ""
    ) -> dict[str, Any]:
        import re
        if request_type in {"video", "delete_video"}:
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_id):
                raise ValueError("youtube_id must be an 11-character YouTube video ID")
            if channel_id < 1:
                raise ValueError("channel_id must be positive")
            return {
                "type": request_type, "youtubeId": youtube_id, "channelId": channel_id,
                "idempotencyKey": secrets.token_urlsafe(24),
            }
        if request_type == "channel":
            from urllib.parse import urlparse
            parsed = urlparse(channel_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}
                or parsed.query or parsed.fragment or parsed.username or parsed.password
                or not re.fullmatch(r"/(?:@[A-Za-z0-9._-]{3,30}|channel/[A-Za-z0-9_-]{20,}|c/[A-Za-z0-9._-]{1,100}|user/[A-Za-z0-9._-]{1,100})", parsed.path)
            ):
                raise ValueError("channel_url must be a canonical HTTPS YouTube handle/channel URL")
            return {"type": request_type, "channelUrl": channel_url, "idempotencyKey": secrets.token_urlsafe(24)}
        raise ValueError("request_type must be video, channel or delete_video")

    @mcp.tool()
    async def youtarr_preview_request(
        request_type: str, youtube_id: str = "", channel_id: int = 0, channel_url: str = ""
    ) -> dict[str, Any]:
        """Preview a Youtarr video/channel/downloaded-video deletion request; nothing is submitted yet."""
        require_permission("operations")
        payload = _youtarr_request_payload(request_type, youtube_id, channel_id, channel_url)
        snapshot = {"service": "youtarr", "payload": payload}
        phrase = f"CONFIRM YOUTARR {request_type.upper()} " + (
            payload.get("youtubeId") or payload.get("channelUrl", "")
        )
        return {
            "preview_token": make_preview_token(snapshot),
            "typed_confirmation": phrase,
            "request": payload,
            "warning": "Youtarr applies the API key's channel grants, content-rating policy, quotas and auto-approval settings. A submitted request may start downloads or delete a downloaded video after approval.",
        }

    @mcp.tool()
    async def youtarr_confirm_request(
        request_type: str, preview_token: str, typed_confirmation: str,
        youtube_id: str = "", channel_id: int = 0, channel_url: str = "",
        idempotency_key: str = "",
    ) -> Any:
        """Submit only the exact Youtarr request shown in a matching preview."""
        require_permission("operations")
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("Pass the idempotency_key returned by youtarr_preview_request")
        payload = _youtarr_request_payload(request_type, youtube_id, channel_id, channel_url)
        payload["idempotencyKey"] = idempotency_key
        snapshot = {"service": "youtarr", "payload": payload}
        expected_token = make_preview_token(snapshot)
        phrase = f"CONFIRM YOUTARR {request_type.upper()} " + (
            payload.get("youtubeId") or payload.get("channelUrl", "")
        )
        if not hmac.compare_digest(preview_token, expected_token):
            raise PermissionError("The Youtarr preview is stale or does not match this request")
        if not hmac.compare_digest(typed_confirmation, phrase):
            raise PermissionError(f"Type exactly: {phrase}")
        endpoints = {
            "video": "/external-api/v1/requests/videos",
            "channel": "/external-api/v1/requests/channels",
            "delete_video": "/external-api/v1/requests/delete-videos",
        }
        return await request("youtarr", "POST", endpoints[request_type], body=payload)

    @mcp.tool()
    async def flaresolverr_list_sessions() -> Any:
        """List active FlareSolverr browser sessions."""
        return await request(
            "flaresolverr", "POST", "/v1", body={"cmd": "sessions.list"}, read_only_post=True
        )

    @mcp.tool()
    async def flaresolverr_request_get(url: str, max_timeout: int = 60000) -> Any:
        """Fetch a public HTTP(S) page through FlareSolverr and return its solved response."""
        require_permission("operations")
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or len(url) > 4096
        ):
            raise ValueError("url must be a valid public HTTP(S) URL without embedded credentials")
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".localhost", ".local", ".internal", ".lan", ".home")
        ):
            raise ValueError("Local and internal hostnames are not allowed")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Private, loopback, link-local and reserved IP addresses are not allowed")
        if max_timeout < 1000 or max_timeout > 120000:
            raise ValueError("max_timeout must be between 1000 and 120000 milliseconds")
        result = await request(
            "flaresolverr",
            "POST",
            "/v1",
            body={"cmd": "request.get", "url": url, "maxTimeout": max_timeout},
            read_only_post=True,
        )
        if isinstance(result, dict) and isinstance(result.get("solution"), dict):
            solution = dict(result["solution"])
            response_text = solution.get("response")
            if isinstance(response_text, str) and len(response_text) > 20000:
                solution["response"] = response_text[:20000] + "\\n...[truncated by HomeLabPilot]"
            result = {**result, "solution": solution}
        return result

    @mcp.tool()
    async def cleanuparr_get_system_status() -> Any:
        """Read Cleanuparr version, uptime and configured *arr instances."""
        return await request("cleanuparr", "GET", "/api/status")

    @mcp.tool()
    async def cleanuparr_get_download_client_status() -> Any:
        """Read configured download-client connection status."""
        return await request("cleanuparr", "GET", "/api/status/download-client")

    @mcp.tool()
    async def cleanuparr_get_arr_status() -> Any:
        """Read connection status for configured *arr instances."""
        return await request("cleanuparr", "GET", "/api/status/arrs")

    @mcp.tool()
    async def cleanuparr_get_events(
        page: int = 1, page_size: int = 50, severity: str | None = None,
        event_type: str | None = None, search: str | None = None,
    ) -> Any:
        """Read Cleanuparr events with pagination and optional severity/type/search filters."""
        if page < 1 or page > 100000 or page_size < 1 or page_size > 100:
            raise ValueError("page must be 1-100000 and page_size must be 1-100")
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        for key, value in (("severity", severity), ("eventType", event_type), ("search", search)):
            if value:
                params[key] = value[:200]
        return await request("cleanuparr", "GET", "/api/events", params=params)

    @mcp.tool()
    async def cleanuparr_get_event_timeline(hours: int = 168) -> Any:
        """Read Cleanuparr event counts over time, for a 1-hour to 1-year window."""
        if hours < 1 or hours > 8760:
            raise ValueError("hours must be between 1 and 8760")
        return await request("cleanuparr", "GET", "/api/events/timeline", params={"hours": hours})

    @mcp.tool()
    async def cleanuparr_get_statistics(hours: int = 168, include_dry_run: bool = False) -> Any:
        """Read aggregated Cleanuparr statistics for a bounded time window."""
        if hours < 1 or hours > 8760:
            raise ValueError("hours must be between 1 and 8760")
        return await request(
            "cleanuparr", "GET", "/api/v2/stats",
            params={"hours": hours, "includeDryRun": include_dry_run},
        )

    @mcp.tool()
    async def cleanuparr_get_recent_strikes(count: int = 10) -> Any:
        """Read recent strike records issued against downloads."""
        if count < 1 or count > 50:
            raise ValueError("count must be between 1 and 50")
        return await request("cleanuparr", "GET", "/api/strikes/recent", params={"count": count})

    @mcp.tool()
    async def cleanuparr_get_strikes(
        page: int = 1, page_size: int = 50, search: str | None = None, strike_type: str | None = None
    ) -> Any:
        """List download strike history with pagination and optional filters."""
        if page < 1 or page > 100000 or page_size < 1 or page_size > 100:
            raise ValueError("page must be 1-100000 and page_size must be 1-100")
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["search"] = search[:200]
        if strike_type:
            params["type"] = strike_type[:80]
        return await request("cleanuparr", "GET", "/api/strikes", params=params)

    @mcp.tool()
    async def cleanuparr_get_jobs() -> Any:
        """Read Cleanuparr scheduled job states and schedules."""
        return await request("cleanuparr", "GET", "/api/jobs")

    @mcp.tool()
    async def cleanuparr_get_manual_event_stats() -> Any:
        """Read counts of Cleanuparr manual events, including unresolved severity totals."""
        return await request("cleanuparr", "GET", "/api/manualevents/stats")

    @mcp.tool()
    async def cleanuparr_get_health() -> Any:
        """Read Cleanuparr health status."""
        return await request("cleanuparr", "GET", "/health")

    @mcp.tool()
    async def maintainerr_get_health() -> Any:
        """Read Maintainerr readiness and database connectivity status."""
        return await request("maintainerr", "GET", "/api/health/ready")

    # BookOrbit workflows (official /api/v1 API; read-only).
    @mcp.tool()
    async def bookorbit_get_health() -> Any:
        """Check BookOrbit API and database health."""
        return await request("bookorbit", "GET", "/api/v1/health")

    @mcp.tool()
    async def bookorbit_get_app_info() -> Any:
        """Read BookOrbit version and server application information."""
        return await request("bookorbit", "GET", "/api/v1/app-info")

    @mcp.tool()
    async def bookorbit_get_current_user() -> Any:
        """Read the identity and effective permissions of the configured API key."""
        return await request("bookorbit", "GET", "/api/v1/auth/me")

    @mcp.tool()
    async def bookorbit_list_libraries() -> Any:
        """List libraries visible to the configured BookOrbit account."""
        return await request("bookorbit", "GET", "/api/v1/libraries")

    @mcp.tool()
    async def bookorbit_get_library_stats(library_id: int) -> Any:
        """Read book and storage statistics for one accessible library."""
        if library_id < 1:
            raise ValueError("library_id must be a positive integer")
        return await request("bookorbit", "GET", f"/api/v1/libraries/{library_id}/stats")

    @mcp.tool()
    async def bookorbit_search_books(query: str, limit: int = 10) -> Any:
        """Search accessible BookOrbit libraries by title, author or other indexed book text."""
        term = query.strip()
        if not term or len(term) > 500:
            raise ValueError("query must contain 1..500 characters")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be 1..20")
        return await request(
            "bookorbit", "GET", "/api/v1/books/search",
            params={"q": term, "limit": limit},
        )

    @mcp.tool()
    async def bookorbit_get_book(book_id: int) -> Any:
        """Read the metadata and available formats for one accessible book."""
        if book_id < 1:
            raise ValueError("book_id must be a positive integer")
        return await request("bookorbit", "GET", f"/api/v1/books/{book_id}")

    @mcp.tool()
    async def bookorbit_get_statistics(library_ids: list[int] | None = None) -> Any:
        """Read BookOrbit reading-library statistics, optionally scoped to library IDs."""
        ids = library_ids or []
        if len(ids) > 50 or any(not isinstance(value, int) or value < 1 for value in ids):
            raise ValueError("library_ids must contain at most 50 positive integers")
        params: dict[str, Any] = {}
        if ids:
            params["libraryIds"] = ids
        return await request("bookorbit", "GET", "/api/v1/statistics/summary", params=params)

    @mcp.tool()
    async def bookorbit_get_format_distribution(library_ids: list[int] | None = None) -> Any:
        """Read the distribution of ebook, PDF, audiobook and comic formats."""
        ids = library_ids or []
        if len(ids) > 50 or any(not isinstance(value, int) or value < 1 for value in ids):
            raise ValueError("library_ids must contain at most 50 positive integers")
        params: dict[str, Any] = {}
        if ids:
            params["libraryIds"] = ids
        return await request("bookorbit", "GET", "/api/v1/statistics/format-distribution", params=params)

    # Agregarr workflows (official /api/v1 API).
    @mcp.tool()
    async def agregarr_get_status() -> Any:
        """Read Agregarr version and update status."""
        return await request("agregarr", "GET", "/api/v1/status")

    @mcp.tool()
    async def agregarr_list_collections() -> Any:
        """List Agregarr collection configurations and their sync/download settings."""
        return await request("agregarr", "GET", "/api/v1/collections")

    @mcp.tool()
    async def agregarr_list_default_hubs() -> Any:
        """List managed default Plex hubs and their visibility/order settings."""
        return await request("agregarr", "GET", "/api/v1/defaulthubs")

    @mcp.tool()
    async def agregarr_list_existing_collections() -> Any:
        """List pre-existing Plex collections managed by Agregarr."""
        return await request("agregarr", "GET", "/api/v1/preexisting")

    @mcp.tool()
    async def agregarr_get_scheduled_jobs() -> Any:
        """List Agregarr scheduled jobs and their next execution times."""
        return await request("agregarr", "GET", "/api/v1/settings/jobs")

    @mcp.tool()
    async def agregarr_get_logs(
        limit: int = 50, offset: int = 0, level: str = "info", search_term: str = ""
    ) -> Any:
        """Read paginated Agregarr logs, optionally filtered by severity and text."""
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("limit must be 1..200 and offset must be non-negative")
        if level not in {"debug", "info", "warn", "error"}:
            raise ValueError("level must be debug, info, warn or error")
        if len(search_term) > 200:
            raise ValueError("search_term must be at most 200 characters")
        params: dict[str, Any] = {"take": limit, "skip": offset, "filter": level}
        if search_term.strip():
            params["search"] = search_term.strip()
        return await request("agregarr", "GET", "/api/v1/settings/logs", params=params)

    @mcp.tool()
    async def agregarr_get_missing_items(
        limit: int = 25, offset: int = 0, status: str = "", media_type: str = "",
        collection_source: str = ""
    ) -> Any:
        """List Agregarr missing-item requests with bounded pagination and optional filters."""
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be non-negative")
        if status and status not in {
            "pending", "approved", "declined", "available", "processing", "failed",
            "partially_available",
        }:
            raise ValueError("unsupported missing-item status")
        if media_type and media_type not in {"movie", "tv"}:
            raise ValueError("media_type must be movie or tv")
        allowed_sources = {
            "trakt", "tmdb", "imdb", "letterboxd", "mdblist", "tautulli", "networks",
            "originals", "overseerr", "anilist", "myanimelist", "radarrtag", "sonarrtag",
            "comingsoon", "filtered_hub", "multi-source",
        }
        if collection_source and collection_source not in allowed_sources:
            raise ValueError("unsupported collection_source")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if media_type:
            params["mediaType"] = media_type
        if collection_source:
            params["collectionSource"] = collection_source
        return await request("agregarr", "GET", "/api/v1/missing-items", params=params)

    @mcp.tool()
    async def agregarr_get_missing_item_stats() -> Any:
        """Read Agregarr missing-item request totals and status/source breakdowns."""
        return await request("agregarr", "GET", "/api/v1/missing-items/stats")

    @mcp.tool()
    async def agregarr_get_dashboard_stats() -> Any:
        """Read Agregarr dashboard totals and collection activity statistics."""
        return await request("agregarr", "GET", "/api/v1/dashboard/stats")

    @mcp.tool()
    async def agregarr_get_dashboard_activity(days: int = 7, limit: int = 10) -> Any:
        """Read recent Agregarr activity and top media from Tautulli."""
        if not 1 <= days <= 365 or not 1 <= limit <= 50:
            raise ValueError("days must be 1..365 and limit must be 1..50")
        return await request(
            "agregarr", "GET", "/api/v1/dashboard/activity",
            params={"days": days, "limit": limit},
        )

    @mcp.tool()
    async def tracearr_get_health() -> Any:
        """Read Tracearr version and connection status for configured media servers."""
        return await request("tracearr", "GET", "/api/v1/public/health")

    @mcp.tool()
    async def tracearr_get_stats(server_id: str = "") -> Any:
        """Read Tracearr dashboard totals for active streams, users, sessions and recent alerts."""
        params: dict[str, Any] = {}
        if server_id:
            import re
            if not re.fullmatch(r"[0-9a-fA-F-]{36}", server_id):
                raise ValueError("server_id must be a UUID")
            params["serverId"] = server_id
        return await request("tracearr", "GET", "/api/v1/public/stats", params=params)

    @mcp.tool()
    async def tracearr_get_activity(
        period: str = "month", server_id: str = "", timezone: str = "Europe/Madrid"
    ) -> Any:
        """Read Tracearr playback trends, concurrent streams, client platforms and quality breakdown."""
        if period not in {"week", "month", "year"}:
            raise ValueError("period must be week, month or year")
        if not timezone or len(timezone) > 100:
            raise ValueError("timezone must be a valid IANA timezone name")
        params: dict[str, Any] = {"period": period, "timezone": timezone}
        if server_id:
            import re
            if not re.fullmatch(r"[0-9a-fA-F-]{36}", server_id):
                raise ValueError("server_id must be a UUID")
            params["serverId"] = server_id
        return await request("tracearr", "GET", "/api/v1/public/activity", params=params)

    @mcp.tool()
    async def tracearr_get_active_streams(server_id: str = "", summary: bool = False) -> Any:
        """List current streams across Plex/Jellyfin/Emby, including playback and transcode details."""
        params: dict[str, Any] = {"summary": str(summary).lower()}
        if server_id:
            import re
            if not re.fullmatch(r"[0-9a-fA-F-]{36}", server_id):
                raise ValueError("server_id must be a UUID")
            params["server_id"] = server_id
        return await request("tracearr", "GET", "/api/v2/public/streams", params=params)

    @mcp.tool()
    async def tracearr_get_watch_history(
        page_size: int = 25, cursor: str = "", user_id: str = "",
        server_id: str = "", media_id: str = "", media_type: str = "",
        since: str = "", until: str = "",
    ) -> Any:
        """Read cursor-paginated playback history with optional user, server, title, type and date filters."""
        import re
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be 1..100")
        params: dict[str, Any] = {"pageSize": page_size}
        for key, value in (("user_id", user_id), ("server_id", server_id), ("media_id", media_id)):
            if value:
                if not re.fullmatch(r"[0-9a-fA-F-]{36}", value):
                    raise ValueError(f"{key} must be a UUID")
                params[key] = value
        if media_type:
            if media_type not in {"movie", "episode", "track", "live", "photo", "trailer", "unknown"}:
                raise ValueError("unsupported media_type")
            params["media_type"] = media_type
        for key, value in (("cursor", cursor), ("since", since), ("until", until)):
            if value:
                if len(value) > 500:
                    raise ValueError(f"{key} is too long")
                params[key] = value
        return await request("tracearr", "GET", "/api/v2/public/history", params=params)

    @mcp.tool()
    async def tracearr_list_servers() -> Any:
        """List configured media servers and their current health in Tracearr."""
        return await request("tracearr", "GET", "/api/v2/public/servers")

    @mcp.tool()
    async def tracearr_list_users(page_size: int = 25, cursor: str = "", include_removed: bool = False) -> Any:
        """List Tracearr user identities and linked media-server accounts."""
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be 1..100")
        params: dict[str, Any] = {"pageSize": page_size, "include_removed": str(include_removed).lower()}
        if cursor:
            if len(cursor) > 500:
                raise ValueError("cursor is too long")
            params["cursor"] = cursor
        return await request("tracearr", "GET", "/api/v2/public/users", params=params)

    @mcp.tool()
    async def tracearr_get_user(user_id: str) -> Any:
        """Read one Tracearr identity and its linked server accounts."""
        import re
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
            raise ValueError("user_id must be a UUID")
        return await request("tracearr", "GET", f"/api/v2/public/users/{user_id}")

    @mcp.tool()
    async def tracearr_get_user_stats(user_id: str) -> Any:
        """Read all-time, 30-day and 7-day plays/watch time plus top genres for one identity."""
        import re
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
            raise ValueError("user_id must be a UUID")
        return await request("tracearr", "GET", f"/api/v2/public/users/{user_id}/stats")

    @mcp.tool()
    async def tracearr_get_recently_added(
        page_size: int = 25, cursor: str = "", server_id: str = "", media_type: str = ""
    ) -> Any:
        """Read recently added items across Tracearr libraries with cursor pagination."""
        import re
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be 1..100")
        params: dict[str, Any] = {"pageSize": page_size}
        if cursor:
            if len(cursor) > 500:
                raise ValueError("cursor is too long")
            params["cursor"] = cursor
        if server_id:
            if not re.fullmatch(r"[0-9a-fA-F-]{36}", server_id):
                raise ValueError("server_id must be a UUID")
            params["server_id"] = server_id
        if media_type:
            if media_type not in {"movie", "episode", "season", "show", "artist", "album", "track", "photo"}:
                raise ValueError("unsupported media_type")
            params["media_type"] = media_type
        return await request("tracearr", "GET", "/api/v2/public/recently-added", params=params)

    @mcp.tool()
    async def tracearr_list_libraries() -> Any:
        """Read per-library item counts, storage sizes and resolution rollups."""
        return await request("tracearr", "GET", "/api/v2/public/libraries")

    @mcp.tool()
    async def tracearr_get_top_media(
        media_type: str = "movie", days: int = 30, sort: str = "plays", page_size: int = 25, cursor: str = ""
    ) -> Any:
        """Rank most watched movies or shows by plays, watch time or viewers."""
        if media_type not in {"movie", "show"} or sort not in {"plays", "watch_time", "viewers"}:
            raise ValueError("media_type must be movie/show and sort must be plays/watch_time/viewers")
        if not 1 <= days <= 365 or not 1 <= page_size <= 1000:
            raise ValueError("days must be 1..365 and page_size 1..1000")
        params: dict[str, Any] = {
            "media_type": media_type, "days": days, "sort": sort, "pageSize": page_size
        }
        if cursor:
            if len(cursor) > 500:
                raise ValueError("cursor is too long")
            params["cursor"] = cursor
        return await request("tracearr", "GET", "/api/v2/public/top-media", params=params)

    @mcp.tool()
    async def tracearr_get_media(media_ref: str) -> Any:
        """Resolve a movie/show/episode to its canonical identity and copies across servers."""
        import re
        if not re.fullmatch(r"(?:[0-9a-fA-F-]{36}|(?:movie|show|episode):(?:imdb|tmdb|tvdb):[A-Za-z0-9_-]{1,32})", media_ref):
            raise ValueError("media_ref must be a UUID or type:provider:id reference")
        return await request("tracearr", "GET", f"/api/v2/public/media/{quote(media_ref, safe='')}")

    @mcp.tool()
    async def tracearr_get_media_stats(media_ref: str) -> Any:
        """Read all-time, 30-day and 7-day play counts and watch time for a title."""
        import re
        if not re.fullmatch(r"(?:[0-9a-fA-F-]{36}|(?:movie|show|episode):(?:imdb|tmdb|tvdb):[A-Za-z0-9_-]{1,32})", media_ref):
            raise ValueError("media_ref must be a UUID or type:provider:id reference")
        return await request("tracearr", "GET", f"/api/v2/public/media/{quote(media_ref, safe='')}/stats")

    @mcp.tool()
    async def tracearr_get_media_watchers(media_ref: str, window: str = "all_time") -> Any:
        """List the users who watched a title, ranked by watch time."""
        import re
        if not re.fullmatch(r"(?:[0-9a-fA-F-]{36}|(?:movie|show|episode):(?:imdb|tmdb|tvdb):[A-Za-z0-9_-]{1,32})", media_ref):
            raise ValueError("media_ref must be a UUID or type:provider:id reference")
        if window not in {"all_time", "last_30", "last_7"}:
            raise ValueError("window must be all_time, last_30 or last_7")
        return await request(
            "tracearr", "GET", f"/api/v2/public/media/{quote(media_ref, safe='')}/watchers",
            params={"window": window},
        )

    @mcp.tool()
    async def tracearr_get_media_children(media_ref: str) -> Any:
        """List seasons of a show or episodes of a season."""
        import re
        if not re.fullmatch(r"(?:[0-9a-fA-F-]{36}|show:tvdb:[A-Za-z0-9_-]{1,32}|show:imdb:[A-Za-z0-9_-]{1,32}|show:tmdb:[A-Za-z0-9_-]{1,32})", media_ref):
            raise ValueError("media_ref must be a UUID or show provider reference")
        return await request("tracearr", "GET", f"/api/v2/public/media/{quote(media_ref, safe='')}/children")

    @mcp.tool()
    async def tracearr_get_user_history(user_id: str, page_size: int = 25, cursor: str = "") -> Any:
        """Read cursor-paginated watch history across every media-server account linked to one identity."""
        import re
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
            raise ValueError("user_id must be a UUID")
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be 1..100")
        params: dict[str, Any] = {"pageSize": page_size}
        if cursor:
            if len(cursor) > 500:
                raise ValueError("cursor is too long")
            params["cursor"] = cursor
        return await request("tracearr", "GET", f"/api/v2/public/users/{user_id}/history", params=params)

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
        if not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+", entity_id):
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
        if not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+", entity_id):
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

    async def _validate_homeassistant_service(domain: str, service: str) -> None:
        import re
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", domain) or not re.fullmatch(r"[a-z_][a-z0-9_]*", service):
            raise ValueError("domain and service must be valid Home Assistant identifiers")
        catalog = await request("homeassistant", "GET", "/api/services")
        if not isinstance(catalog, list):
            raise RuntimeError("Home Assistant returned an unexpected service catalogue")
        if not any(
            isinstance(item, dict)
            and item.get("domain") == domain
            and isinstance(item.get("services"), dict)
            and service in item["services"]
            for item in catalog
        ):
            raise ValueError(f"Home Assistant service {domain}.{service} is not currently registered")

    async def _homeassistant_action_snapshot(
        domain: str, service: str, entity_ids: list[str], service_data: dict[str, Any]
    ) -> dict[str, Any]:
        import re
        if not 1 <= len(entity_ids) <= 50:
            raise ValueError("entity_ids must contain 1..50 entities")
        if any(not isinstance(x, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+", x) for x in entity_ids):
            raise ValueError("Every entity_id must use the domain.entity_id format")
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("entity_ids must be unique")
        if not isinstance(service_data, dict) or len(service_data) > 50:
            raise ValueError("service_data must be an object with at most 50 fields")
        if "entity_id" in service_data or "target" in service_data:
            raise ValueError("Pass target entities only through entity_ids")
        if len(str(service_data)) > 10000:
            raise ValueError("service_data is too large")
        await _validate_homeassistant_service(domain, service)
        return {
            "service": "homeassistant",
            "domain": domain,
            "action": service,
            "entity_ids": sorted(entity_ids),
            "service_data": service_data,
        }

    @mcp.tool()
    async def homeassistant_preview_service(
        domain: str, service: str, entity_ids: list[str], service_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Preview a Home Assistant service call; no device or automation is changed until confirmed."""
        require_permission("admin")
        payload = await _homeassistant_action_snapshot(domain, service, entity_ids, service_data or {})
        phrase = f"CONFIRM HOME ASSISTANT {domain}.{service} " + ", ".join(payload["entity_ids"])
        return {
            "preview_token": make_preview_token(payload),
            "typed_confirmation": phrase,
            "domain": domain,
            "service": service,
            "entity_ids": payload["entity_ids"],
            "service_data": payload["service_data"],
            "warning": "This invokes the selected Home Assistant service and may operate devices, locks, covers, scripts or automations.",
        }

    @mcp.tool()
    async def homeassistant_confirm_service(
        domain: str, service: str, entity_ids: list[str], preview_token: str,
        typed_confirmation: str, service_data: dict[str, Any] | None = None,
    ) -> Any:
        """Execute only the exact Home Assistant service call shown in a matching preview."""
        require_permission("admin")
        payload = await _homeassistant_action_snapshot(domain, service, entity_ids, service_data or {})
        expected_token = make_preview_token(payload)
        phrase = f"CONFIRM HOME ASSISTANT {domain}.{service} " + ", ".join(payload["entity_ids"])
        if not hmac.compare_digest(preview_token, expected_token):
            raise PermissionError("The Home Assistant preview is stale or does not match this action")
        if not hmac.compare_digest(typed_confirmation, phrase):
            raise PermissionError(f"Type exactly: {phrase}")
        return await request(
            "homeassistant", "POST", f"/api/services/{domain}/{service}",
            body={"entity_id": payload["entity_ids"], **payload["service_data"]},
        )

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

    async def _cloudflare_dns_change_snapshot(
        action: str, zone_id: str, record_type: str, name: str,
        content: str = "", ttl: int = 1, proxied: bool = False, record_id: str = "",
    ) -> dict[str, Any]:
        import ipaddress
        import re
        if action not in {"create", "update", "delete"}:
            raise ValueError("action must be create, update or delete")
        if not re.fullmatch(r"[A-Fa-f0-9]{32}", zone_id):
            raise ValueError("zone_id must be a 32-character Cloudflare zone ID")
        if action in {"update", "delete"} and not re.fullmatch(r"[A-Fa-f0-9]{32}", record_id):
            raise ValueError("update/delete require a 32-character record_id")
        existing = None
        if action in {"update", "delete"}:
            response = await request("cloudflare", "GET", f"/zones/{zone_id}/dns_records/{record_id}")
            existing = response.get("result") if isinstance(response, dict) else None
            if not isinstance(existing, dict) or existing.get("id") != record_id:
                raise ValueError("Cloudflare DNS record was not found in the selected zone")
        if action != "delete":
            allowed = {"A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"}
            if record_type.upper() not in allowed:
                raise ValueError(f"record_type must be one of: {', '.join(sorted(allowed))}")
            if not name or len(name) > 253 or any(ch.isspace() for ch in name):
                raise ValueError("name must be a DNS name of 1..253 characters")
            if not content or len(content) > 4096:
                raise ValueError("content must contain 1..4096 characters")
            if ttl != 1 and not 60 <= ttl <= 86400:
                raise ValueError("ttl must be 1 (automatic) or 60..86400 seconds")
            if record_type.upper() == "A":
                ipaddress.IPv4Address(content)
            elif record_type.upper() == "AAAA":
                ipaddress.IPv6Address(content)
            elif record_type.upper() == "CNAME" and ("/" in content or " " in content):
                raise ValueError("CNAME content must be a hostname, not a URL")
        return {
            "service": "cloudflare",
            "action": action,
            "zone_id": zone_id,
            "record_id": record_id if action != "create" else "",
            "record_type": record_type.upper() if action != "delete" else (existing or {}).get("type", ""),
            "name": name if action != "delete" else (existing or {}).get("name", ""),
            "content": content if action != "delete" else (existing or {}).get("content", ""),
            "ttl": ttl if action != "delete" else (existing or {}).get("ttl", 1),
            "proxied": proxied if action != "delete" else (existing or {}).get("proxied", False),
            "existing": existing,
        }

    @mcp.tool()
    async def cloudflare_preview_dns_change(
        action: str, zone_id: str, record_type: str = "", name: str = "",
        content: str = "", ttl: int = 1, proxied: bool = False, record_id: str = "",
    ) -> dict[str, Any]:
        """Preview creating, updating or deleting one Cloudflare DNS record; no change is made."""
        require_permission("admin")
        payload = await _cloudflare_dns_change_snapshot(
            action, zone_id, record_type, name, content, ttl, proxied, record_id
        )
        phrase = f"CONFIRM CLOUDFLARE DNS {action.upper()} {payload['record_type']} {payload['name']} {zone_id}"
        if record_id:
            phrase += f" {record_id}"
        return {
            "preview_token": make_preview_token(payload),
            "typed_confirmation": phrase,
            "record": {k: payload[k] for k in ("record_type", "name", "content", "ttl", "proxied")},
            "existing_record": payload["existing"],
            "warning": "DNS changes can interrupt access to services or mail for this domain.",
        }

    @mcp.tool()
    async def cloudflare_confirm_dns_change(
        action: str, zone_id: str, preview_token: str, typed_confirmation: str,
        record_type: str = "", name: str = "", content: str = "",
        ttl: int = 1, proxied: bool = False, record_id: str = "",
    ) -> Any:
        """Execute only the exact Cloudflare DNS change shown in a matching preview."""
        require_permission("admin")
        payload = await _cloudflare_dns_change_snapshot(
            action, zone_id, record_type, name, content, ttl, proxied, record_id
        )
        expected_token = make_preview_token(payload)
        phrase = f"CONFIRM CLOUDFLARE DNS {action.upper()} {payload['record_type']} {payload['name']} {zone_id}"
        if record_id:
            phrase += f" {record_id}"
        if not hmac.compare_digest(preview_token, expected_token):
            raise PermissionError("The Cloudflare DNS preview is stale or does not match this action")
        if not hmac.compare_digest(typed_confirmation, phrase):
            raise PermissionError(f"Type exactly: {phrase}")
        path = f"/zones/{zone_id}/dns_records"
        if action == "delete":
            return await request("cloudflare", "DELETE", f"{path}/{record_id}")
        body = {
            "type": payload["record_type"], "name": payload["name"],
            "content": payload["content"], "ttl": payload["ttl"],
            "proxied": payload["proxied"],
        }
        if action == "create":
            return await request("cloudflare", "POST", path, body=body)
        return await request("cloudflare", "PUT", f"{path}/{record_id}", body=body)

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


    # tinyMediaManager HTTP API: read-only inspection plus explicitly previewed
    # metadata tasks. The service executes tasks asynchronously after POST.
    TMM_SECTIONS = {"movie", "tvshow", "movieset"}
    TMM_ACTIONS = {
        "update", "scrape", "writeNfo", "downloadMissingArtwork",
        "fetchRatings", "reloadMediaInfo", "rename", "downloadTrailer",
        "downloadSubtitle", "calculateChecksum", "detectAspectRatio",
        "setWatched", "postProcess", "updateKodi", "syncTrakt", "syncSimkl",
    }
    TMM_SCOPES = {
        "new", "path", "dataSource", "tmdbId", "imdbId", "tvdbId",
        "unscraped", "all", "single", "name",
    }

    def _tmm_tasks(section: str, tasks: Any) -> list[dict[str, Any]]:
        if section not in TMM_SECTIONS:
            raise ValueError("section must be movie, tvshow or movieset")
        batch = tasks if isinstance(tasks, list) else [tasks]
        if not batch or len(batch) > 20:
            raise ValueError("Provide between 1 and 20 tinyMediaManager tasks")
        normalized: list[dict[str, Any]] = []
        for index, task in enumerate(batch):
            if not isinstance(task, dict):
                raise ValueError(f"Task {index + 1} must be an object")
            if set(task) - {"action", "scope", "args"}:
                raise ValueError(f"Task {index + 1} contains unsupported fields")
            action = task.get("action")
            if action not in TMM_ACTIONS:
                raise ValueError(f"Task {index + 1}: unsupported action; allowed: {', '.join(sorted(TMM_ACTIONS))}")
            scope = task.get("scope", {"name": "all"})
            if not isinstance(scope, dict) or set(scope) - {"name", "args"}:
                raise ValueError(f"Task {index + 1} scope must contain only name and args")
            scope_name = scope.get("name", "all")
            if scope_name not in TMM_SCOPES:
                raise ValueError(f"Task {index + 1}: unsupported scope")
            scope_args = scope.get("args", [])
            if not isinstance(scope_args, (list, str, int)):
                raise ValueError(f"Task {index + 1} scope.args must be a list, string or integer")
            args = task.get("args", {})
            if not isinstance(args, dict):
                raise ValueError(f"Task {index + 1} args must be an object")
            normalized.append({"action": action, "scope": scope, **({"args": args} if args else {})})
        return normalized

    @mcp.tool()
    async def tinymediamanager_get_status() -> Any:
        """Read tinyMediaManager version, running/busy state and queued/running tasks."""
        return await request("tinymediamanager", "GET", "/api/system")

    @mcp.tool()
    async def tinymediamanager_get_api_docs() -> Any:
        """Read tinyMediaManager's live OpenAPI description, including supported actions and scopes."""
        return await request("tinymediamanager", "GET", "/api/docs")

    @mcp.tool()
    async def tinymediamanager_preview_tasks(section: str, tasks: Any) -> dict[str, Any]:
        """Preview 1-20 metadata tasks; no work is queued until the matching confirmation."""
        require_permission("admin")
        normalized = _tmm_tasks(section, tasks)
        snapshot = {"service": "tinymediamanager", "section": section, "tasks": normalized}
        phrase = f"CONFIRM TINYMEDIAMANAGER {section.upper()} {len(normalized)} TASKS"
        return {
            "preview_token": make_preview_token(snapshot),
            "typed_confirmation": phrase,
            "section": section,
            "task_count": len(normalized),
            "tasks": normalized,
            "warning": "Tasks may modify metadata, NFO files, artwork, subtitles or media filenames depending on the selected actions.",
        }

    @mcp.tool()
    async def tinymediamanager_run_tasks(
        section: str, tasks: Any, preview_token: str, typed_confirmation: str
    ) -> Any:
        """Queue only the exact tinyMediaManager task batch previously previewed and confirmed."""
        require_permission("admin")
        normalized = _tmm_tasks(section, tasks)
        snapshot = {"service": "tinymediamanager", "section": section, "tasks": normalized}
        expected_token = make_preview_token(snapshot)
        expected_phrase = f"CONFIRM TINYMEDIAMANAGER {section.upper()} {len(normalized)} TASKS"
        if not hmac.compare_digest(preview_token, expected_token):
            raise PermissionError("The tinyMediaManager task preview is stale or does not match this batch")
        if not hmac.compare_digest(typed_confirmation, expected_phrase):
            raise PermissionError(f"Type exactly: {expected_phrase}")
        body: Any = normalized[0] if len(normalized) == 1 else normalized
        return await request("tinymediamanager", "POST", f"/api/{section}", body=body)

    @mcp.tool()
    async def cleanuparr_get_health() -> Any:
        """Read Cleanuparr liveness without requiring authentication."""
        return await request("cleanuparr", "GET", "/health")

    @mcp.tool()
    async def cleanuparr_get_readiness() -> Any:
        """Read Cleanuparr readiness, including dependent service checks."""
        return await request("cleanuparr", "GET", "/health/ready")

    @mcp.tool()
    async def maintainerr_get_app_status() -> Any:
        """Read Maintainerr version and update availability."""
        return await request("maintainerr", "GET", "/api/app/status")

    @mcp.tool()
    async def maintainerr_get_timezone() -> Any:
        """Read the timezone configured inside the Maintainerr process."""
        return await request("maintainerr", "GET", "/api/app/timezone")

    @mcp.tool()
    async def maintainerr_get_health() -> Any:
        """Read Maintainerr readiness, including its database health."""
        return await request("maintainerr", "GET", "/api/health/ready")

    @mcp.tool()
    async def maintainerr_get_live_health() -> Any:
        """Read the Maintainerr liveness probe without checking the database."""
        return await request("maintainerr", "GET", "/api/health/live")

    @mcp.tool()
    async def maintainerr_get_task_status(task_name: str) -> Any:
        """Read whether a named scheduled Maintainerr task is currently running."""
        allowed = {
            "Collection Handler", "Collection Log Cleaner", "Rule Maintenance",
            "Overlay Handler", "Notification Timer", "Version Notification", "Telemetry Ping",
        }
        if task_name not in allowed:
            raise ValueError(f"task_name must be one of: {', '.join(sorted(allowed))}")
        from urllib.parse import quote
        return await request("maintainerr", "GET", f"/api/tasks/{quote(task_name, safe='')}")

    TIDARR_DOWNLOAD_TYPES = {"album", "track", "video", "playlist", "mix", "artist", "artist_videos"}

    def _tidarr_download_item(item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("item must be an object")
        if set(item) - {"id", "url", "type", "quality"}:
            raise ValueError("item accepts only id, url, type and quality")
        item_id = str(item.get("id", "")).strip()
        kind = item.get("type")
        url = item.get("url")
        quality = item.get("quality")
        if not item_id or len(item_id) > 128:
            raise ValueError("item.id must contain 1-128 characters")
        if kind not in TIDARR_DOWNLOAD_TYPES:
            raise ValueError(f"type must be one of: {', '.join(sorted(TIDARR_DOWNLOAD_TYPES))}")
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("item.url must be a Tidal URL")
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"listen.tidal.com", "tidal.com", "www.tidal.com"}
            or not parsed.path.startswith(f"/{kind.removesuffix('_videos')}/")
        ):
            raise ValueError("url must be an HTTPS Tidal URL matching the selected type")
        normalized = {"id": item_id, "url": url, "type": kind, "status": "queue_download"}
        if quality is not None:
            if quality not in {"max", "high", "normal", "low"}:
                raise ValueError("quality must be max, high, normal or low")
            normalized["quality"] = quality
        return normalized

    @mcp.tool()
    async def tidarr_get_auth_status() -> Any:
        """Check whether Tidarr requires authentication and which authentication mode is active."""
        return await request("tidarr", "GET", "/api/is-auth-active")

    @mcp.tool()
    async def tidarr_get_download_queue(offset: int = 0, limit: int = 50) -> Any:
        """List Tidarr downloads and their statuses, with bounded pagination."""
        if offset < 0 or offset > 100000 or limit < 1 or limit > 200:
            raise ValueError("offset must be 0-100000 and limit must be 1-200")
        return await request("tidarr", "GET", "/api/queue/list", params={"offset": offset, "limit": limit})

    @mcp.tool()
    async def tidarr_get_queue_status() -> Any:
        """Read Tidarr queue pause and rate-limit batch status."""
        return await request("tidarr", "GET", "/api/queue/status")

    @mcp.tool()
    async def tidarr_get_download_history() -> Any:
        """Read Tidarr download history; availability depends on ENABLE_HISTORY."""
        return await request("tidarr", "GET", "/api/history/list")

    @mcp.tool()
    async def tidarr_get_sync_list() -> Any:
        """List playlists and mixes configured for automatic synchronization."""
        return await request("tidarr", "GET", "/api/sync/list")

    @mcp.tool()
    async def tidarr_preview_action(action: str, item: Any = None) -> dict[str, Any]:
        """Preview adding a Tidal item or a queue/sync operation; nothing changes until confirmed."""
        require_permission("operations")
        allowed = {"add_download", "pause_queue", "resume_queue", "retry_failed", "sync_now"}
        if action not in allowed:
            raise ValueError(f"action must be one of: {', '.join(sorted(allowed))}")
        payload = _tidarr_download_item(item) if action == "add_download" else None
        snapshot = {"service": "tidarr", "action": action, "item": payload}
        phrase = f"CONFIRM TIDARR {action.upper().replace('_', ' ')}"
        if payload:
            phrase += f" {payload['type'].upper()} {payload['id']}"
        return {
            "preview_token": make_preview_token(snapshot),
            "typed_confirmation": phrase,
            "action": action,
            "item": payload,
            "warning": "Adding a download starts Tidarr's download workflow; queue actions affect pending downloads.",
        }

    @mcp.tool()
    async def tidarr_confirm_action(
        action: str, preview_token: str, typed_confirmation: str, item: Any = None
    ) -> Any:
        """Execute only the exact Tidarr action shown in a matching preview."""
        require_permission("operations")
        allowed = {"add_download", "pause_queue", "resume_queue", "retry_failed", "sync_now"}
        if action not in allowed:
            raise ValueError(f"action must be one of: {', '.join(sorted(allowed))}")
        payload = _tidarr_download_item(item) if action == "add_download" else None
        snapshot = {"service": "tidarr", "action": action, "item": payload}
        expected_token = make_preview_token(snapshot)
        phrase = f"CONFIRM TIDARR {action.upper().replace('_', ' ')}"
        if payload:
            phrase += f" {payload['type'].upper()} {payload['id']}"
        if not hmac.compare_digest(preview_token, expected_token):
            raise PermissionError("The Tidarr preview is stale or does not match this action")
        if not hmac.compare_digest(typed_confirmation, phrase):
            raise PermissionError(f"Type exactly: {phrase}")
        if action == "add_download":
            return await request("tidarr", "POST", "/api/save", body={"item": payload})
        paths = {
            "pause_queue": "/api/queue/pause",
            "resume_queue": "/api/queue/resume",
            "retry_failed": "/api/retry-failed",
            "sync_now": "/api/sync/trigger",
        }
        return await request("tidarr", "POST", paths[action])

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

    async def dashboard_read(service: str, operation: str, **kwargs: Any) -> Any:
        """Expose a fixed allowlist of read-only integration calls to the web dashboard."""
        readers = {
            "tdarr": {
                "status": tdarr_get_status,
                "nodes": tdarr_get_nodes,
                "search_files": tdarr_search_files,
                "job_reports": tdarr_list_job_reports,
                "job_report": tdarr_get_job_report,
            },
            "questarr": {
                "status": questarr_get_status,
                "library": questarr_get_library,
            },
            "frigate": {
                "status": frigate_get_status,
                "events": frigate_list_events,
                "review": frigate_list_review_items,
                "review_summary": frigate_get_review_summary,
            },
            "plex": {
                "libraries": plex_get_library_sections,
                "recent": plex_get_recently_added_all,
                "recent_section": plex_get_recently_added,
                "sessions": plex_get_active_sessions,
                "on_deck": plex_get_on_deck,
            },
            "jellyfin": {
                "server_info": jellyfin_get_server_info,
                "libraries": jellyfin_get_libraries,
                "sessions": jellyfin_get_active_sessions,
                "search": jellyfin_search_items,
            },
            "seerr": {
                "status": seerr_get_status,
                "requests": seerr_get_requests,
                "application_data": seerr_get_application_data_status,
                "search": seerr_search_media,
            },
            "immich": {
                "statistics": immich_get_server_statistics,
                "albums": immich_get_albums,
                "search": immich_search_assets,
            },
            "romm": {
                "platforms": romm_get_platforms,
                "roms": romm_list_roms,
                "search": romm_search_roms,
                "rom": romm_get_rom,
                "collections": romm_list_collections,
            },
            "homeassistant": {
                "config": homeassistant_get_config,
                "states": homeassistant_list_states,
                "state": homeassistant_get_state,
                "history": homeassistant_get_history,
                "services": homeassistant_list_services,
            },
            "bookorbit": {
                "health": bookorbit_get_health,
                "libraries": bookorbit_list_libraries,
                "statistics": bookorbit_get_statistics,
                "format_distribution": bookorbit_get_format_distribution,
                "library_stats": bookorbit_get_library_stats,
                "search": bookorbit_search_books,
                "book": bookorbit_get_book,
            },
            "tidarr": {
                "status": tidarr_get_auth_status,
                "queue_status": tidarr_get_queue_status,
                "queue": tidarr_get_download_queue,
                "history": tidarr_get_download_history,
                "sync_list": tidarr_get_sync_list,
            },
            "youtarr": {
                "capabilities": youtarr_get_capabilities,
                "channels": youtarr_list_channels,
                "videos": youtarr_list_videos,
                "video": youtarr_get_video,
                "requests": youtarr_list_requests,
                "request_detail": youtarr_get_request,
            },
            "pulsarr": {
                "health": pulsarr_get_health,
                "approval_requests": pulsarr_get_approval_requests,
                "content_router_rules": pulsarr_list_content_router_rules,
            },
            "cleanuparr": {
                "health": cleanuparr_get_readiness,
                "system": cleanuparr_get_system_status,
                "events": cleanuparr_get_events,
                "event_timeline": cleanuparr_get_event_timeline,
                "statistics": cleanuparr_get_statistics,
                "recent_strikes": cleanuparr_get_recent_strikes,
                "strikes": cleanuparr_get_strikes,
                "jobs": cleanuparr_get_jobs,
                "manual_event_stats": cleanuparr_get_manual_event_stats,
            },
            "maintainerr": {
                "health": maintainerr_get_health,
                "app_status": maintainerr_get_app_status,
                "timezone": maintainerr_get_timezone,
                "task_status": maintainerr_get_task_status,
            },
            "agregarr": {
                "status": agregarr_get_status,
                "collections": agregarr_list_collections,
                "dashboard_stats": agregarr_get_dashboard_stats,
                "activity": agregarr_get_dashboard_activity,
                "missing_items": agregarr_get_missing_items,
                "missing_item_stats": agregarr_get_missing_item_stats,
                "scheduled_jobs": agregarr_get_scheduled_jobs,
                "logs": agregarr_get_logs,
            },
            "tracearr": {
                "health": tracearr_get_health,
                "stats": tracearr_get_stats,
                "activity": tracearr_get_activity,
                "active_streams": tracearr_get_active_streams,
                "servers": tracearr_list_servers,
                "libraries": tracearr_list_libraries,
                "recently_added": tracearr_get_recently_added,
                "watch_history": tracearr_get_watch_history,
                "top_media": tracearr_get_top_media,
            },
            "cloudflare": {
                "zones": cloudflare_list_zones,
                "dns_records": cloudflare_list_dns_records,
            },
            "transmission": {
                "session": transmission_get_session,
                "statistics": transmission_get_statistics,
                "torrents": transmission_list_torrents,
                "torrent_details": transmission_list_torrents,
            },
            "flaresolverr": {
                "sessions": flaresolverr_list_sessions,
                "request_get": flaresolverr_request_get,
            },
            "tinymediamanager": {
                "status": tinymediamanager_get_status,
                "tasks": tinymediamanager_get_status,
                "api_docs": tinymediamanager_get_api_docs,
            },
        }
        service_readers = readers.get(service)
        if service_readers is None or operation not in service_readers:
            raise ValueError("Unsupported dashboard read operation")
        return await service_readers[operation](**kwargs)

    status_checks.dashboard_read = dashboard_read
    return status_checks
