"""Sanitization helpers for provider-native data.

Provider metadata (task metadata, session material, device payloads) may embed
secrets. The prototype never inlines raw provider payloads into a provenance
record; artifacts reference material by locator and content hash only. These
helpers provide defensive redaction for the cases where a short provider string
must be surfaced, and a scan used by tests to assert no secret leaks into a
record.
"""

from __future__ import annotations

import hashlib
import re
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


# Credentials embedded in free text, e.g. provider error messages that echo a
# signed URL or request header: "...?token=abc", "Authorization: Bearer abc".
_TEXT_PATTERNS = (
    re.compile(
        r"(?i)((?:^|[?&;\s])(?:[a-z0-9_.-]*(?:token|secret|password|passwd|signature|credential|"
        r"api[_-]?key|access[_-]?key|sig))=)[^&\s\"',;]+"
    ),
    re.compile(r"(?i)(\b(?:bearer|basic|apikey|token)\s+)[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)(\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s\"',;&]+"),
    re.compile(r"()\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
)


def redact_text(text: str | None) -> str | None:
    """Mask credentials that appear inside free text."""

    if not text:
        return text
    for pattern in _TEXT_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    return text


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


_PROGRAM_PLACEHOLDER = re.compile(r"^<program redacted sha256=([0-9a-f]{64}) bytes=(\d+)>$")


def program_digest(text: str) -> tuple[str, int]:
    """SHA-256 and byte size of program text, or of the original behind a capture digest.

    Sanitized captures replace program text by ``<program redacted sha256=… bytes=…>``;
    the digest then identifies the original program rather than the placeholder.
    """

    match = _PROGRAM_PLACEHOLDER.match(text)
    if match:
        return match.group(1), int(match.group(2))
    data = text.encode("utf-8")
    return hashlib.sha256(data).hexdigest(), len(data)


__all__ = [
    "REDACTED",
    "is_secret_key",
    "redact",
    "redact_text",
    "find_secret_keys",
    "program_digest",
]
