"""Sanitization of captured live provider responses before they are committed."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any

from ..redaction import redact

ACCOUNT_PLACEHOLDER = "000000000000"

# AWS account IDs appear inside ARNs (``arn:aws:<svc>:<region>:<account>:``) and in
# the default Braket result bucket name (``amazon-braket-<region>-<account>``).
_ARN_ACCOUNT = re.compile(r"(arn:aws:[a-z0-9-]+:[a-z0-9-]*:)(\d{12})(:)")
_BUCKET_ACCOUNT = re.compile(r"(amazon-braket-[a-z0-9-]+?-)(\d{12})\b")


# Fields holding program text. Submitted and compiled programs can embed
# proprietary algorithms, so captures keep only a digest and size. Empty strings
# are kept as-is because "present but empty" is itself a finding.
PROGRAM_FIELDS = frozenset({"source", "compiledProgram", "compiled_circuit"})


def digest_program(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"<program redacted sha256={digest} bytes={len(text.encode('utf-8'))}>"


def mask_identifiers(text: str) -> str:
    text = _ARN_ACCOUNT.sub(rf"\g<1>{ACCOUNT_PLACEHOLDER}\g<3>", text)
    return _BUCKET_ACCOUNT.sub(rf"\g<1>{ACCOUNT_PLACEHOLDER}", text)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def sanitize(value: Any) -> Any:
    """JSON-safe copy: secrets redacted, account identifiers masked, programs digested."""

    def _mask(item: Any) -> Any:
        if isinstance(item, str):
            return mask_identifiers(item)
        if isinstance(item, dict):
            return {
                mask_identifiers(str(k)): (
                    digest_program(v)
                    if k in PROGRAM_FIELDS and isinstance(v, str) and v
                    else _mask(v)
                )
                for k, v in item.items()
            }
        if isinstance(item, list):
            return [_mask(v) for v in item]
        return item

    return _mask(redact(to_jsonable(value)))
