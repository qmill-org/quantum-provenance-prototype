"""Stage C: real provider interface changes, replayed before and after.

IonQ API v0.3 -> v0.4 renamed ``execution_time_ms`` to ``execution_duration_ms``
(the change reaches the adapters). qiskit-ibm-runtime moved job inputs from a
PUB list to ``schema_version`` v2.0; that change is absorbed by the retrieval
layer, so it is checked there.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..comparison.run import tagged_records
from .seam import _v2_record

DRIFT_CODES = {
    "expected_provider_field_missing",
    "unrecognized_result_format",
    "unrecognized_provider_schema",
}


def _outcome(record: dict[str, Any] | None, expected: Any) -> str:
    if record is None:
        return "no_record"
    value = (record.get("execution") or {}).get("run_duration_ms")
    if value is not None:
        return "delivered" if value == expected else "wrong"
    codes = {w["code"] for w in record.get("warnings") or []}
    return "flagged" if codes & DRIFT_CODES else "silently_lost"


def run_stage_c(root: Path) -> dict[str, Any]:
    before = json.loads((root / "tests/fixtures/ionq/completed.json").read_text())
    after = json.loads(
        (root / "captures/ionq/01a1f2eb-d155-7632-bc4e-f340de096f01/fixture.json").read_text()
    )
    # Control: a rename that no adapter knows (synthetic, stated as such).
    future = copy.deepcopy(after)
    metadata = future["snapshot"]["metadata"]
    metadata["execution_runtime_ms"] = metadata.pop("execution_duration_ms")
    variants = {
        "v0.3 (execution_time_ms)": (before, before["snapshot"]["metadata"]["execution_time_ms"]),
        "v0.4 (execution_duration_ms), real capture": (
            after,
            after["snapshot"]["metadata"]["execution_duration_ms"],
        ),
        "unknown future rename (control)": (future, None),
    }
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for name, (fixture, _) in variants.items():
            path = Path(tmp) / f"{len(paths)}.json"
            path.write_text(json.dumps(fixture))
            paths[name] = path
        v1 = tagged_records("v0.1.0", list(paths.values()))
    ionq = {
        name: {
            "V1": _outcome(v1.get(str(paths[name])), expected),
            "V2": _outcome(_v2_record(fixture), expected),
        }
        for name, (fixture, expected) in variants.items()
    }
    return {"ionq_run_duration": ionq, "ibm_input_schema": _ibm_inputs()}


def _ibm_inputs() -> dict[str, Any]:
    """The IBM retrieval layer reads requested shots from both input layouts."""

    from qiskit import QuantumCircuit

    from ..live.ibm import _requested_shots

    circuit = QuantumCircuit(1, 1)
    pubs = {"pubs": [(circuit, None, 4096)]}

    class Program:
        shots = 64
        items: list = []
        passthrough_data = {"post_processor": {"shots": 1000}}

    v2 = {"schema_version": "v2.0", "quantum_program": Program()}
    return {
        "pubs (qiskit-ibm-runtime <= 0.4x)": _requested_shots(pubs),
        "v2.0 QuantumProgram (0.52)": _requested_shots(v2),
    }
