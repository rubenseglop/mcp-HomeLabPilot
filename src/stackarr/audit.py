"""Small persistent audit log for StackARR-initiated write operations."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_LOGGER = logging.getLogger("stackarr.audit")


def _path() -> Path:
    return Path(os.getenv("STACKARR_AUDIT_DB_PATH", "/tmp/stackarr-audit.sqlite3"))


def record_event(
    operation: str,
    *,
    service: str = "stackarr",
    target: str = "",
    outcome: str = "succeeded",
    source: str = "mcp",
) -> None:
    """Persist metadata only; request bodies, credentials and tokens are never recorded."""
    path = _path()
    try:
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(path, timeout=5) as db:
                db.execute(
                    """CREATE TABLE IF NOT EXISTS operation_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        occurred_at TEXT NOT NULL,
                        source TEXT NOT NULL,
                        service TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        target TEXT NOT NULL,
                        outcome TEXT NOT NULL
                    )"""
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS ix_operation_events_time "
                    "ON operation_events(id DESC)"
                )
                db.execute(
                    "INSERT INTO operation_events "
                    "(occurred_at, source, service, operation, target, outcome) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        source[:32], service[:64], operation[:120], target[:240], outcome[:32],
                    ),
                )
                db.execute(
                    "DELETE FROM operation_events WHERE id <= "
                    "(SELECT MAX(id) - 10000 FROM operation_events)"
                )
    except Exception:
        # An audit-storage outage must not turn a successful media operation into a failure.
        _LOGGER.exception("Could not persist operation audit event")


def list_events(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("limit must be 1..500 and offset must be non-negative")
    path = _path()
    if not path.exists():
        return []
    with _LOCK, sqlite3.connect(path, timeout=5) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT id, occurred_at, source, service, operation, target, outcome "
            "FROM operation_events ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]
