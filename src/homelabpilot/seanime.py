"""Read-only native integration for Seanime."""
from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx


def register_seanime_tools(mcp: Any, timeout: float = 15) -> None:
    """Register read-only Seanime MCP tools."""

    async def request(path: str) -> Any:
        base_url = os.getenv("SEANIME_URL", "").strip().rstrip("/")
        if not base_url:
            raise ValueError("Seanime is not configured: set SEANIME_URL")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("SEANIME_URL must start with http:// or https://")
        password = os.getenv("SEANIME_PASSWORD", "")
        headers = {"Accept": "application/json"}
        if password:
            headers["X-Seanime-Token"] = hashlib.sha256(password.encode("utf-8")).hexdigest()
        async with httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=False
        ) as client:
            response = await client.get(f"{base_url}{path}")
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"text": response.text[:12000]}

    def data_of(payload: Any) -> Any:
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def compact_entry(entry: Any) -> Any:
        if not isinstance(entry, dict):
            return entry
        media = entry.get("media")
        if not isinstance(media, dict):
            return {
                key: entry[key] for key in ("id", "mediaId", "status", "progress")
                if key in entry
            }
        title = media.get("title")
        if isinstance(title, dict):
            title = title.get("userPreferred") or title.get("romaji") or title.get("english")
        library = entry.get("libraryData") or {}
        list_data = entry.get("listData") or {}
        return {
            "media": {
                key: value for key, value in {
                    "id": media.get("id"),
                    "idMal": media.get("idMal"),
                    "title": title,
                    "siteUrl": media.get("siteUrl"),
                    "type": media.get("type"),
                    "format": media.get("format"),
                    "season": media.get("season"),
                    "seasonYear": media.get("seasonYear"),
                    "episodes": media.get("episodes"),
                    "meanScore": media.get("meanScore"),
                    "genres": media.get("genres"),
                    "coverImage": media.get("coverImage"),
                }.items() if value is not None
            },
            "mediaId": entry.get("mediaId"),
            "libraryData": {
                key: library.get(key) for key in
                ("allFilesLocked", "sharedPath", "unwatchedCount", "mainFileCount")
                if key in library
            } if isinstance(library, dict) else {},
            "listData": {
                key: list_data.get(key) for key in
                ("status", "progress", "score", "createdAt", "updatedAt")
                if key in list_data
            } if isinstance(list_data, dict) else {},
        }

    async def library_payload() -> dict:
        payload = data_of(await request("/api/v1/library/collection"))
        return payload if isinstance(payload, dict) else {}

    @mcp.tool()
    async def seanime_get_status() -> dict:
        """Check Seanime server availability, version and password protection."""
        payload = data_of(await request("/api/v1/status"))
        if not isinstance(payload, dict):
            return {"response": payload}
        return {
            key: payload.get(key) for key in
            ("version", "serverReady", "isOffline", "serverHasPassword")
            if key in payload
        }

    @mcp.tool()
    async def seanime_get_library(limit: int = 100) -> dict:
        """Read Seanime's local anime library with compact AniList and local-file metadata."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        payload = await library_payload()
        raw_lists = payload.get("lists", [])
        lists: Any = []
        if isinstance(raw_lists, list):
            for library_list in raw_lists:
                if not isinstance(library_list, dict):
                    continue
                entries = library_list.get("entries", [])
                lists.append({
                    "type": library_list.get("type"),
                    "status": library_list.get("status"),
                    "entries": [
                        compact_entry(item) for item in entries[:limit]
                    ] if isinstance(entries, list) else [],
                })
        elif isinstance(raw_lists, dict):
            # Compatibility with older Seanime responses that grouped entries by key.
            lists = {
                name: [compact_entry(item) for item in entries[:limit]]
                if isinstance(entries, list) else []
                for name, entries in raw_lists.items()
            }
        return {
            "stats": payload.get("stats"),
            "lists": lists,
            "continueWatchingCount": len(payload.get("continueWatchingList", []))
            if isinstance(payload.get("continueWatchingList"), list) else None,
        }

    @mcp.tool()
    async def seanime_audit_library(limit: int = 500) -> dict:
        """Audit local Seanime library for shared folders and suspicious file/episode counts; read-only."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")

        payload = await library_payload()
        raw_lists = payload.get("lists", [])
        entries: list[dict[str, Any]] = []
        if isinstance(raw_lists, list):
            for library_list in raw_lists:
                if not isinstance(library_list, dict):
                    continue
                raw_entries = library_list.get("entries", [])
                if isinstance(raw_entries, list):
                    for entry in raw_entries:
                        if isinstance(entry, dict):
                            entries.append(entry)
        elif isinstance(raw_lists, dict):
            for raw_entries in raw_lists.values():
                if isinstance(raw_entries, list):
                    entries.extend(entry for entry in raw_entries if isinstance(entry, dict))

        entries = entries[:limit]
        by_path: dict[str, list[dict[str, Any]]] = {}
        count_warnings: list[dict[str, Any]] = []
        missing_path: list[dict[str, Any]] = []

        for entry in entries:
            media = entry.get("media") if isinstance(entry.get("media"), dict) else {}
            library = entry.get("libraryData") if isinstance(entry.get("libraryData"), dict) else {}
            title_data = media.get("title")
            if isinstance(title_data, dict):
                title = title_data.get("userPreferred") or title_data.get("romaji") or title_data.get("english") or "Sin título"
            else:
                title = title_data or "Sin título"

            path = library.get("sharedPath")
            item = {
                "title": title,
                "mediaId": media.get("id") or entry.get("mediaId"),
                "format": media.get("format"),
                "episodes": media.get("episodes"),
                "mainFileCount": library.get("mainFileCount"),
                "unwatchedCount": library.get("unwatchedCount"),
                "sharedPath": path,
            }

            if isinstance(path, str) and path.strip():
                normalized = path.strip().rstrip("/\\").casefold()
                by_path.setdefault(normalized, []).append(item)
            else:
                missing_path.append({"title": title, "mediaId": item["mediaId"]})

            episodes = item["episodes"]
            files = item["mainFileCount"]
            if isinstance(episodes, (int, float)) and episodes > 0 and isinstance(files, (int, float)) and files > 0:
                ratio = files / episodes
                fmt = str(item["format"] or "").upper()
                if ratio >= 2:
                    count_warnings.append({
                        **item,
                        "reason": "Hay bastantes más archivos principales que episodios declarados.",
                        "filesPerEpisode": round(ratio, 2),
                        "severity": "review",
                    })
                elif ratio <= 0.25 and episodes >= 4:
                    count_warnings.append({
                        **item,
                        "reason": "Hay muchos menos archivos principales que episodios declarados.",
                        "filesPerEpisode": round(ratio, 2),
                        "severity": "review",
                    })
                if fmt in {"OVA", "SPECIAL"} and episodes <= 2 and files >= 5:
                    count_warnings.append({
                        **item,
                        "reason": "OVA/especial de pocos episodios asociado a muchos archivos locales; comprobar posible emparejamiento incorrecto.",
                        "filesPerEpisode": round(ratio, 2),
                        "severity": "high",
                    })

        shared_paths = []
        for group in by_path.values():
            if len(group) > 1:
                shared_paths.append({
                    "sharedPath": group[0]["sharedPath"],
                    "entries": group,
                    "severity": "high",
                    "reason": "Varias entradas de AniList apuntan a la misma carpeta local.",
                })

        return {
            "summary": {
                "entriesAudited": len(entries),
                "sharedFolderGroups": len(shared_paths),
                "fileEpisodeCountWarnings": len(count_warnings),
                "entriesWithoutSharedPath": len(missing_path),
            },
            "sharedFolders": shared_paths,
            "countWarnings": count_warnings,
            "entriesWithoutSharedPath": missing_path,
            "note": "Las diferencias entre archivos y episodios son indicios, no pruebas: pueden existir especiales, versiones, extras o episodios divididos. Esta auditoría no modifica archivos ni asociaciones.",
        }

    @mcp.tool()
    async def seanime_get_continue_watching(limit: int = 50) -> dict:
        """Read Seanime's continue-watching list with bounded results."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        payload = await library_payload()
        items = payload.get("continueWatchingList", [])
        if not isinstance(items, list):
            return {"count": 0, "items": []}
        return {"count": len(items), "items": [compact_entry(item) for item in items[:limit]]}

    @mcp.tool()
    async def seanime_get_anilist_collection(limit: int = 100) -> Any:
        """Read Seanime's AniList collection and list progress."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        payload = data_of(await request("/api/v1/anilist/collection/raw"))
        if isinstance(payload, list):
            return {"count": len(payload), "items": [compact_entry(item) for item in payload[:limit]]}
        if isinstance(payload, dict):
            result = dict(payload)
            for key, value in result.items():
                if isinstance(value, list):
                    result[key] = [compact_entry(item) for item in value[:limit]]
            return result
        return payload

    @mcp.tool()
    async def seanime_get_downloader() -> dict:
        """Read Seanime automatic downloader rules, queue and profiles; does not start downloads."""
        def as_list(value: Any) -> Any:
            # Seanime may serialize an empty Go slice as JSON null.
            return [] if value is None else value

        return {
            "rules": as_list(data_of(await request("/api/v1/auto-downloader/rules"))),
            "queue": as_list(data_of(await request("/api/v1/auto-downloader/items"))),
            "profiles": as_list(data_of(await request("/api/v1/auto-downloader/profiles"))),
        }
