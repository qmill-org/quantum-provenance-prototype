"""Regenerate the canonical example provenance records under docs/.

The example records in ``artifact/examples/`` are the
adapter output for the sanitized ``completed.json`` fixtures. They are checked
into the repo (and validated by ``test_provenance_contract.py``), so they must
be regenerated whenever the adapters, the model, or the fixtures change.

Usage::

    # rewrite the example records in place
    python -m qmill_quantum_provenance.generate_examples

    # verify the checked-in records are up to date (non-zero exit on drift),
    # ignoring the wall-clock generated_at/retrieved_at fields
    python -m qmill_quantum_provenance.generate_examples --check

Runs entirely off the sanitized fixtures with no network or credentials.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from .contract import validate_record
from .evaluation import (
    _default_fixture_paths,
    _examples_dir,
    _load_fixture,
    build_request,
    build_service,
)

# Wall-clock fields that legitimately change on every run and must be ignored
# when checking whether the checked-in records are up to date.
_VOLATILE_FIELDS = ("generated_at", "retrieved_at")


def _build_records() -> dict[str, dict[str, Any]]:
    """Return {provider: serialized record} built from the default fixtures."""

    fixtures = {
        provider: _load_fixture(path) for provider, path in _default_fixture_paths().items()
    }
    service = build_service(fixtures)

    records: dict[str, dict[str, Any]] = {}
    for provider, fixture in fixtures.items():
        request = build_request(provider, fixture)
        record, _created = service.create_record(request)
        payload = record.to_dict()
        validate_record(payload)
        records[provider] = payload
    return records


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2) + "\n"


def _stable(payload: dict[str, Any]) -> dict[str, Any]:
    stable = copy.deepcopy(payload)
    for field in _VOLATILE_FIELDS:
        stable.pop(field, None)
    return stable


def _example_path(provider: str) -> Path:
    return _examples_dir() / f"{provider}-completed.json"


def generate(check: bool = False) -> int:
    """Write (or, when ``check`` is set, verify) the example records.

    Returns 0 on success. In check mode, returns 1 if any checked-in record is
    missing or differs from freshly generated output (ignoring volatile fields).
    """

    records = _build_records()
    drifted: list[str] = []

    for provider, payload in records.items():
        path = _example_path(provider)
        if check:
            if not path.exists():
                drifted.append(f"{path.name} (missing)")
                continue
            current = json.loads(path.read_text(encoding="utf-8"))
            if _stable(current) != _stable(payload):
                drifted.append(path.name)
        else:
            path.write_text(_serialize(payload), encoding="utf-8")
            print(f"wrote {path.relative_to(_examples_dir().parents[1])}")

    if check:
        if drifted:
            print("Example records are out of date: " + ", ".join(sorted(drifted)))
            print("Run: python -m qmill_quantum_provenance.generate_examples")
            return 1
        print("Example records are up to date.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the checked-in records are up to date instead of writing them.",
    )
    args = parser.parse_args(argv)
    return generate(check=args.check)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["generate", "main"]
