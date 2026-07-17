"""Access to the canonical provenance contract and record validation.

The OpenAPI document ``openapi.json`` is the source of truth. It is shipped as
package data (``qmill_quantum_provenance/openapi.json``) so records can be
validated both from a source checkout and from an installed wheel.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

_PACKAGE = "qmill_quantum_provenance"
_CONTRACT_FILENAME = "openapi.json"


def contract_path() -> Path:
    """Return a filesystem path to the packaged contract document."""

    return Path(str(resources.files(_PACKAGE).joinpath(_CONTRACT_FILENAME)))


@lru_cache(maxsize=1)
def load_contract() -> dict[str, Any]:
    packaged = resources.files(_PACKAGE).joinpath(_CONTRACT_FILENAME)
    return json.loads(packaged.read_text(encoding="utf-8"))


def record_schema() -> dict[str, Any]:
    return load_contract()["components"]["schemas"]["ProvenanceRecord"]


def validate_record(record: dict[str, Any]) -> None:
    """Validate a serialized record against the canonical schema.

    Raises ``jsonschema.ValidationError`` on failure.
    """

    import jsonschema

    contract = load_contract()
    resolver = jsonschema.RefResolver.from_schema(contract)
    validator = jsonschema.Draft202012Validator(record_schema(), resolver=resolver)
    validator.validate(record)


__all__ = ["contract_path", "load_contract", "record_schema", "validate_record"]
