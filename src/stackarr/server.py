"""StackARR MCP: full-control API bridge for media applications.

The server never accepts a caller-supplied hostname. Requests are restricted to
service base URLs configured by the operator, preventing the MCP tools from
becoming a general-purpose HTTP proxy.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("StackARR")
TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))

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
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        raise ValueError("path must be an absolute API path beginning with one '/'")
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


@mcp.tool()
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
        login.raise_for_status()
        if login.text.strip() != "Ok.":
            raise RuntimeError("qBittorrent rejected the configured credentials")
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


def main() -> None:
    """Run StackARR as an MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
