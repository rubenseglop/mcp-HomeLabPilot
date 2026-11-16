"""MCP server exposing read-only diagnostics for a self-hosted *arr stack."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("StackARR")

TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "8"))

SERVICES: dict[str, dict[str, str]] = {
    "radarr": {
        "url": os.getenv("RADARR_URL", "").rstrip("/"),
        "key": os.getenv("RADARR_API_KEY", ""),
        "status_path": "/api/v3/system/status",
        "queue_path": "/api/v3/queue?page=1&pageSize=100&includeUnknownMovieItems=true",
        "header": "X-Api-Key",
    },
    "sonarr": {
        "url": os.getenv("SONARR_URL", "").rstrip("/"),
        "key": os.getenv("SONARR_API_KEY", ""),
        "status_path": "/api/v3/system/status",
        "queue_path": "/api/v3/queue?page=1&pageSize=100&includeUnknownSeriesItems=true",
        "header": "X-Api-Key",
    },
    "prowlarr": {
        "url": os.getenv("PROWLARR_URL", "").rstrip("/"),
        "key": os.getenv("PROWLARR_API_KEY", ""),
        "status_path": "/api/v1/system/status",
        "queue_path": "",
        "header": "X-Api-Key",
    },
    "bazarr": {
        "url": os.getenv("BAZARR_URL", "").rstrip("/"),
        "key": os.getenv("BAZARR_API_KEY", ""),
        "status_path": "/api/system/status",
        "queue_path": "",
        "header": "X-Api-Key",
    },
}


def _configured(name: str) -> bool:
    service = SERVICES[name]
    return bool(service["url"] and service["key"])


async def _arr_get(name: str, path: str) -> Any:
    service = SERVICES[name]
    if not _configured(name):
        raise RuntimeError(f"{name} is not configured (URL or API key missing)")
    headers = {service["header"]: service["key"]}
    url = urljoin(service["url"] + "/", path.lstrip("/"))
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()


async def _qbittorrent_get(path: str) -> Any:
    base_url = os.getenv("QBITTORRENT_URL", "").rstrip("/")
    username = os.getenv("QBITTORRENT_USERNAME", "")
    password = os.getenv("QBITTORRENT_PASSWORD", "")
    if not (base_url and username and password):
        raise RuntimeError("qBittorrent is not configured (URL, username or password missing)")

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        login = await client.post(
            f"{base_url}/api/v2/auth/login",
            data={"username": username, "password": password},
        )
        login.raise_for_status()
        if login.text.strip() != "Ok.":
            raise RuntimeError("qBittorrent rejected the configured credentials")
        response = await client.get(f"{base_url}{path}", cookies=login.cookies)
        response.raise_for_status()
        return response.json() if response.content else {}


def _error_summary(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "request timed out"
    if isinstance(exc, httpx.RequestError):
        return "connection failed"
    return str(exc)


@mcp.tool()
async def stack_status() -> dict[str, Any]:
    """Check connectivity and report versions for configured *arr services and qBittorrent."""
    results: dict[str, Any] = {}

    async def check_arr(name: str) -> None:
        try:
            data = await _arr_get(name, SERVICES[name]["status_path"])
            results[name] = {
                "ok": True,
                "version": data.get("version"),
                "app_name": data.get("appName"),
                "branch": data.get("branch"),
            }
        except Exception as exc:  # Return per-service failures without hiding other results.
            results[name] = {"ok": False, "error": _error_summary(exc)}

    async def check_qbit() -> None:
        try:
            version = await _qbittorrent_get("/api/v2/app/version")
            results["qbittorrent"] = {"ok": True, "version": version}
        except Exception as exc:
            results["qbittorrent"] = {"ok": False, "error": _error_summary(exc)}

    await asyncio.gather(*(check_arr(name) for name in SERVICES), check_qbit())
    return {
        "mode": "read-only",
        "services": results,
        "note": "A failed check may indicate a URL, API key, credential, network, or reverse-proxy issue.",
    }


@mcp.tool()
async def get_download_queue() -> dict[str, Any]:
    """Read active Radarr, Sonarr and qBittorrent queues without changing anything."""
    results: dict[str, Any] = {}

    async def arr_queue(name: str) -> None:
        path = SERVICES[name]["queue_path"]
        if not path:
            return
        try:
            payload = await _arr_get(name, path)
            records = payload.get("records", []) if isinstance(payload, dict) else []
            results[name] = {
                "total_records": payload.get("totalRecords", len(records)),
                "records": [
                    {
                        "title": item.get("title"),
                        "status": item.get("status"),
                        "trackedDownloadStatus": item.get("trackedDownloadStatus"),
                        "trackedDownloadState": item.get("trackedDownloadState"),
                        "statusMessages": item.get("statusMessages", []),
                        "errorMessage": item.get("errorMessage"),
                        "outputPath": item.get("outputPath"),
                        "downloadId": item.get("downloadId"),
                    }
                    for item in records
                ],
            }
        except Exception as exc:
            results[name] = {"error": _error_summary(exc)}

    async def qbit_queue() -> None:
        try:
            records = await _qbittorrent_get("/api/v2/torrents/info")
            results["qbittorrent"] = [
                {
                    "name": item.get("name"),
                    "state": item.get("state"),
                    "progress": item.get("progress"),
                    "dlspeed": item.get("dlspeed"),
                    "upspeed": item.get("upspeed"),
                    "eta": item.get("eta"),
                    "save_path": item.get("save_path"),
                    "category": item.get("category"),
                    "tags": item.get("tags"),
                    "hash": item.get("hash"),
                }
                for item in records
            ]
        except Exception as exc:
            results["qbittorrent"] = {"error": _error_summary(exc)}

    await asyncio.gather(arr_queue("radarr"), arr_queue("sonarr"), qbit_queue())
    return {
        "mode": "read-only",
        "queues": results,
        "note": "Queue data is a snapshot; no queue or download actions are performed.",
    }


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
