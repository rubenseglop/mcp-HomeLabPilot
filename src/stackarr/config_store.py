"""Encrypted, allowlisted persistence for dashboard-managed app connections.

The encrypted file lives on the existing writable /data volume. Secret values are
never returned by the read API. Environment variables remain a bootstrap source;
saved dashboard values override them at process startup.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

APP_CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "radarr": ("RADARR_URL", "RADARR_API_KEY"),
    "sonarr": ("SONARR_URL", "SONARR_API_KEY"),
    "prowlarr": ("PROWLARR_URL", "PROWLARR_API_KEY"),
    "bazarr": ("BAZARR_URL", "BAZARR_API_KEY"),
    "lidarr": ("LIDARR_URL", "LIDARR_API_KEY"),
    "scryer": ("SCRYER_URL", "SCRYER_API_KEY"),
    "qbittorrent": ("QBITTORRENT_URL", "QBITTORRENT_USERNAME", "QBITTORRENT_PASSWORD"),
    "plex": ("PLEX_URL", "PLEX_TOKEN"),
    "jellyfin": ("JELLYFIN_URL", "JELLYFIN_API_KEY"),
    "seerr": ("SEERR_URL", "SEERR_API_KEY"),
    "immich": ("IMMICH_URL", "IMMICH_API_KEY"),
    "romm": ("ROMM_URL", "ROMM_API_TOKEN"),
    "bookorbit": ("BOOKORBIT_URL", "BOOKORBIT_API_KEY"),
    "tinymediamanager": ("TINYMEDIAMANAGER_URL", "TINYMEDIAMANAGER_API_KEY"),
    "tidarr": ("TIDARR_URL", "TIDARR_API_KEY"),
    "transmission": ("TRANSMISSION_URL", "TRANSMISSION_USERNAME", "TRANSMISSION_PASSWORD"),
    "flaresolverr": ("FLARESOLVERR_URL",),
    "pulsarr": ("PULSARR_URL", "PULSARR_API_KEY"),
    "cleanuparr": ("CLEANUPARR_URL", "CLEANUPARR_API_KEY"),
    "maintainerr": ("MAINTAINERR_URL",),
    "agregarr": ("AGREGARR_URL", "AGREGARR_API_KEY"),
    "tracearr": ("TRACEARR_URL", "TRACEARR_API_KEY"),
    "cloudflare": ("CLOUDFLARE_API_URL", "CLOUDFLARE_API_TOKEN"),
    "tdarr": ("TDARR_URL", "TDARR_API_KEY"),
    "youtarr": ("YOUTARR_URL", "YOUTARR_API_KEY"),
    "questarr": ("QUESTARR_URL", "QUESTARR_API_KEY"),
    "homeassistant": ("HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN"),
    "frigate": ("FRIGATE_URL", "FRIGATE_API_KEY"),
    "postgres": ("POSTGRES_HOST", "POSTGRES_PORT"),
    "redis": ("REDIS_HOST", "REDIS_PORT"),
    "recyclarr": ("RECYCLARR_CONTAINER",),
}

CONFIG_PATH = Path(os.getenv("STACKARR_CONFIG_PATH", "/data/app-config.enc"))
_SECRET_NAME = re.compile(r"(?:API_KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL)", re.I)
_HOSTNAME = re.compile(r"^[A-Za-z0-9_.:-]{1,253}$")
_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _cipher() -> Fernet:
    """Derive an encryption key from a stable operator secret."""
    secret = (
        os.getenv("STACKARR_CONFIG_ENCRYPTION_KEY", "").strip()
        or os.getenv("MCP_AUTH_TOKEN", "").strip()
    )
    if len(secret) < 32:
        raise ValueError(
            "Set STACKARR_CONFIG_ENCRYPTION_KEY (32+ characters) or a 32-character MCP_AUTH_TOKEN"
        )
    material = hashlib.sha256(
        b"HomeLabPilot app configuration encryption v1:" + secret.encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def _read_store() -> dict[str, dict[str, str]]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        plaintext = _cipher().decrypt(CONFIG_PATH.read_bytes())
        data = json.loads(plaintext)
    except (OSError, InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Cannot decrypt HomeLabPilot app configuration. Keep the encryption key unchanged."
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Stored HomeLabPilot app configuration has an invalid format")
    cleaned: dict[str, dict[str, str]] = {}
    for app_id, values in data.items():
        if app_id not in APP_CONFIG_FIELDS or not isinstance(values, dict):
            continue
        allowed = set(APP_CONFIG_FIELDS[app_id])
        cleaned[app_id] = {
            key: value for key, value in values.items()
            if key in allowed and isinstance(value, str)
        }
    return cleaned


def load_saved_config() -> None:
    """Apply persisted values over bootstrap environment values at startup."""
    for values in _read_store().values():
        for key, value in values.items():
            os.environ[key] = value


def _field_kind(key: str) -> str:
    if _SECRET_NAME.search(key):
        return "secret"
    if key.endswith("_URL"):
        return "url"
    if key.endswith("_PORT"):
        return "port"
    if key.endswith("_HOST"):
        return "host"
    return "text"


def _display_value(key: str, value: str) -> str:
    if _field_kind(key) == "url":
        try:
            parsed = urlsplit(value)
            if not parsed.scheme or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                return ""
            host = parsed.hostname
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            if parsed.port:
                host += f":{parsed.port}"
            return f"{parsed.scheme}://{host}{parsed.path.rstrip('/')}"
        except ValueError:
            return ""
    return value


def get_app_config() -> dict[str, Any]:
    """Return editable non-secret values and presence flags, never secret contents."""
    result: dict[str, Any] = {}
    for app_id, keys in APP_CONFIG_FIELDS.items():
        fields = []
        for key in keys:
            value = os.getenv(key, "")
            kind = _field_kind(key)
            secret = kind == "secret"
            display_value = "" if secret else _display_value(key, value)
            fields.append({
                "key": key,
                "label": key.removeprefix(app_id.upper() + "_").replace("_", " ").title(),
                "kind": kind,
                "value": display_value,
                "configured": bool(value),
                "redacted": bool(value) and kind == "url" and not display_value,
                "secret_set": bool(value) if secret else False,
            })
        result[app_id] = {"fields": fields}
    return result


def _validate_value(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    if len(value) > 4096 or any(ord(char) < 32 and char not in "\t" for char in value):
        raise ValueError(f"{key} contains invalid characters or is too long")
    value = value.strip()
    kind = _field_kind(key)
    if not value:
        return ""
    if kind == "url":
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(char.isspace() for char in value)
        ):
            raise ValueError(f"{key} must be an http(s) URL without embedded credentials, query or fragment")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError(f"{key} contains an invalid port") from exc
    elif kind == "port":
        try:
            port = int(value)
        except ValueError as exc:
            raise ValueError(f"{key} must be a port between 1 and 65535") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{key} must be a port between 1 and 65535")
        value = str(port)
    elif key == "RECYCLARR_CONTAINER" and not _CONTAINER.fullmatch(value):
        raise ValueError("RECYCLARR_CONTAINER must be a valid container name")
    elif kind == "host" and not _HOSTNAME.fullmatch(value):
        raise ValueError(f"{key} must be a hostname or IP address")
    return value


def save_app_config(
    app_id: str, values: dict[str, Any], clear_secrets: list[str] | None = None
) -> dict[str, Any]:
    """Validate and atomically persist one app's allowlisted settings."""
    if app_id not in APP_CONFIG_FIELDS:
        raise ValueError("This application does not support connection configuration")
    if not isinstance(values, dict):
        raise ValueError("values must be a JSON object")
    allowed = set(APP_CONFIG_FIELDS[app_id])
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("Unsupported configuration field(s): " + ", ".join(sorted(unknown)))
    clear = clear_secrets or []
    if not isinstance(clear, list) or any(key not in allowed or _field_kind(key) != "secret" for key in clear):
        raise ValueError("clear_secrets may contain only secret fields belonging to this application")

    store = _read_store()
    current = {
        key: os.getenv(key, "")
        for key in APP_CONFIG_FIELDS[app_id]
        if os.getenv(key, "")
    }
    current.update(store.get(app_id, {}))
    for key, raw in values.items():
        value = _validate_value(key, raw)
        if not value:
            continue  # Empty fields preserve the existing environment or saved value.
        current[key] = value
    for key in clear:
        current[key] = ""

    store[app_id] = current
    encrypted = _cipher().encrypt(json.dumps(store, sort_keys=True).encode("utf-8"))
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".app-config-", dir=str(CONFIG_PATH.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, CONFIG_PATH)
        os.chmod(CONFIG_PATH, 0o600)
        directory_fd = os.open(CONFIG_PATH.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    for key, value in current.items():
        os.environ[key] = value
    return {
        "app_id": app_id,
        "configured_fields": [key for key, value in current.items() if value],
        "secret_fields_set": [
            key for key, value in current.items() if value and _field_kind(key) == "secret"
        ],
    }
