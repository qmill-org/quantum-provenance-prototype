"""API keys: stored as SHA-256 hashes, bound to a tenant and permissions."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

PERMISSIONS = frozenset({"read", "write"})


@dataclass(frozen=True)
class Principal:
    tenant: str
    permissions: frozenset[str]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class KeyRing:
    """Verifies presented keys against configured hashes in constant time per entry."""

    def __init__(self, entries: list[dict]) -> None:
        self._entries = []
        for entry in entries:
            permissions = frozenset(entry["permissions"])
            if not permissions <= PERMISSIONS or not entry.get("tenant"):
                raise ValueError("API key entry needs a tenant and read/write permissions")
            self._entries.append((entry["sha256"], Principal(entry["tenant"], permissions)))

    @classmethod
    def from_file(cls, path: str | Path) -> KeyRing:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def verify(self, presented: str) -> Principal | None:
        digest = hash_key(presented)
        found = None
        for stored, principal in self._entries:
            if hmac.compare_digest(stored, digest):
                found = principal
        return found
