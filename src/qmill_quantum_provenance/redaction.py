"""Sanitization helpers for provider-native data.

Provider metadata (task metadata, session material, device payloads) may embed
secrets. The prototype never inlines raw provider payloads into a provenance
record; artifacts reference material by locator and content hash only. These
helpers provide defensive redaction for the cases where a short provider string
must be surfaced, and a scan used by tests to assert no secret leaks into a
record.
"""

from __future__ import annotations

from typing import Any


REDACTED = "***redacted***"

# Substrings that mark a key (or JSON field) as sensitive.
_SECRET_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "session_token",
    "client_secret",
    "aws_secret",
)


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def redact(value: Any, _depth: int = 0) -> Any:
    """Return a deep copy of ``value`` with secret-looking fields masked."""

    if _depth > 12:
        return REDACTED
    if isinstance(value, dict):
        return {
            key: (REDACTED if is_secret_key(str(key)) else redact(item, _depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, _depth + 1) for item in value]
    return value


def find_secret_keys(value: Any, _path: str = "") -> list[str]:
    """Return JSON-pointer-ish paths of any secret-looking keys found."""

    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{_path}/{key}"
            if is_secret_key(str(key)):
                found.append(child)
            found.extend(find_secret_keys(item, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(find_secret_keys(item, f"{_path}/{index}"))
    return found


__all__ = ["REDACTED", "is_secret_key", "redact", "find_secret_keys"]
