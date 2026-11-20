"""WP-E5: transport faults (stage A) and seam faults (stage B, arm V2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qmill_quantum_provenance.experiments import seam
from qmill_quantum_provenance.experiments.transport import run_stage_a

ROOT = Path(__file__).resolve().parents[1]


def test_every_transport_fault_becomes_the_expected_integration_error() -> None:
    unexpected = [c for c in run_stage_a() if c["outcome"] not in ("as_expected", "not_applicable")]
    assert unexpected == []


@pytest.mark.parametrize("base", sorted(seam.BASES))
def test_seam_faults_never_crash_fabricate_or_give_a_wrong_reason(base: str) -> None:
    inventory = json.loads((ROOT / "artifact/attribute-inventory.json").read_text())
    validator = seam._validator(
        json.loads((ROOT / "src/qmill_quantum_provenance/openapi.json").read_text())
    )
    fixture = json.loads((ROOT / "captures" / seam.BASES[base] / "fixture.json").read_text())
    base_record = seam._v2_record(fixture)
    failures = []
    for family, case, spec in seam.cases():
        mutated = seam.mutate(fixture, family, spec)
        if mutated is None:
            continue
        measured = seam.measure(
            seam._v2_record(mutated),
            base_record,
            inventory,
            validator,
            fixture["provider"],
            family,
            spec,
        )
        bad = [m for m in ("M1_crash",) if measured.get(m)] + [
            m for m in ("M3_valid", "M4_honest", "M5_reason") if measured.get(m) is False
        ]
        if bad:
            failures.append((case, bad))
    assert failures == []
