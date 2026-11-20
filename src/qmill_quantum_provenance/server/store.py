"""SQLite record store: every assembly of a job is kept as a new version."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MAX_VERSION = 2**63 - 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    tenant TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    request_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (record_id, version)
)
"""


@dataclass(frozen=True)
class StoredRecord:
    record_id: str
    version: int
    tenant: str
    generated_at: str
    retrieved_at: str
    request: dict[str, Any]
    record: dict[str, Any]


class RecordStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, check_same_thread=False)

    def add(self, tenant: str, request: dict[str, Any], record: dict[str, Any]) -> int:
        with self._lock, self._connect() as db:
            (latest,) = db.execute(
                "SELECT COALESCE(MAX(version), 0) FROM records WHERE record_id = ?",
                (record["record_id"],),
            ).fetchone()
            version = latest + 1
            db.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record["record_id"],
                    version,
                    tenant,
                    record["generated_at"],
                    record["retrieved_at"],
                    json.dumps(request),
                    json.dumps(record),
                ),
            )
        return version

    def get(self, record_id: str, version: int | None = None) -> StoredRecord | None:
        if version is not None and version > _MAX_VERSION:
            return None  # cannot exist; SQLite integers are 64-bit
        query = "SELECT * FROM records WHERE record_id = ?"
        params: tuple[Any, ...] = (record_id,)
        if version is None:
            query += " ORDER BY version DESC LIMIT 1"
        else:
            query += " AND version = ?"
            params += (version,)
        with self._connect() as db:
            row = db.execute(query, params).fetchone()
        return _row(row) if row else None

    def versions(self, record_id: str) -> list[StoredRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM records WHERE record_id = ? ORDER BY version", (record_id,)
            ).fetchall()
        return [_row(row) for row in rows]


def _row(row: tuple[Any, ...]) -> StoredRecord:
    record_id, version, tenant, generated, retrieved, request, record = row
    return StoredRecord(
        record_id, version, tenant, generated, retrieved, json.loads(request), json.loads(record)
    )
