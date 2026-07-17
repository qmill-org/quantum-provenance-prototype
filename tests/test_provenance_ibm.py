"""End-to-end IBM Quantum provenance flow over sanitized fixtures.

Covers schema validation, IBM-specific mapping (queue/run/total execution split
and nearest-available characterization), a partial record (characterization
unavailable with a single-total execution fallback), redaction, and idempotent
create/get semantics for the in-process service.
"""

from __future__ import annotations

import json
from pathlib import Path

from qmill_quantum_provenance import (
    CreateProvenanceRecordRequest,
    ProvenanceService,
)
from qmill_quantum_provenance.adapters.ibm import (
    IBMProvenanceAdapter,
)
from qmill_quantum_provenance.contract import validate_record
from qmill_quantum_provenance.registry import (
    ProvenanceAdapterRegistry,
)
from qmill_quantum_provenance.replay import ReplayIntegrationAdapter

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ibm"


def _load(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def _service(fixture: dict) -> ProvenanceService:
    registry = ProvenanceAdapterRegistry()
    registry.register(
        "ibm",
        lambda: IBMProvenanceAdapter(ReplayIntegrationAdapter(fixture)),
    )
    return ProvenanceService(registry=registry)


def _request(fixture: dict, **kwargs) -> CreateProvenanceRecordRequest:
    return CreateProvenanceRecordRequest(
        provider="ibm",
        external_job_id=str(fixture["external_job_id"]),
        region=fixture.get("region"),
        **kwargs,
    )


def test_completed_record_validates_against_contract() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, created = service.create_record(_request(fixture))

    assert created is True
    validate_record(record.to_dict())


def test_ibm_mapping_normalizes_expected_fields() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, _ = service.create_record(_request(fixture))
    payload = record.to_dict()
    validate_record(payload)

    assert record.job.status == "completed"
    assert record.job.shots == 4096
    assert record.device.type == "qpu"
    assert record.device.qubit_count == 156
    # IBM operates its own hardware, so platform and hardware provider agree.
    assert record.device.platform_provider == "ibm_quantum"
    assert record.device.hardware_provider == "ibm"
    assert record.results.available is True
    assert record.results.measurement_counts["00000"] == 2013

    # IBM-specific: execution timing is split into queue/run/total.
    # created 09:15:00 -> running 09:15:42 -> finished 09:15:47.5.
    assert record.execution is not None
    assert record.execution.queue_duration_ms == 42000
    assert record.execution.run_duration_ms == 5250
    assert record.execution.total_duration_ms == 47250

    # IBM-specific: characterization is the nearest-available snapshot with
    # typed metrics (no provider guarantee it was in force during execution).
    assert record.characterization is not None
    assert record.characterization.association.value == "nearest_available"
    assert record.characterization.metrics is not None
    metric_names = {m.name for m in record.characterization.metrics}
    assert {"median_t1_us", "median_t2_us", "median_readout_error"} <= metric_names
    t1 = next(m for m in record.characterization.metrics if m.name == "median_t1_us")
    assert t1.unit == "microseconds"

    statuses = {(e.path, e.status.value) for e in record.evidence}
    assert ("/job/status", "provider_supplied") in statuses
    assert ("/execution/queue_duration_ms", "derived") in statuses
    assert ("/execution/run_duration_ms", "derived") in statuses
    assert ("/characterization", "provider_supplied") in statuses

    # Compiled ISA + provider-native artifacts are hash-only passthrough.
    roles = {artifact.role.value for artifact in record.artifacts}
    assert "compiled" in roles
    assert "provider_native" in roles


def test_partial_record_marks_characterization_unavailable() -> None:
    fixture = _load("completed_no_calibration.json")
    service = _service(fixture)
    record, _ = service.create_record(_request(fixture))
    payload = record.to_dict()

    validate_record(payload)
    assert "characterization" not in payload

    unavailable = [
        e
        for e in record.evidence
        if e.path == "/characterization" and e.status.value == "unavailable"
    ]
    assert len(unavailable) == 1
    assert unavailable[0].reason is not None

    # No Runtime timestamps -> execution falls back to a single total duration.
    assert record.execution is not None
    assert record.execution.queue_duration_ms is None
    assert record.execution.run_duration_ms is None
    assert record.execution.total_duration_ms == 12000


def test_no_secret_material_leaks_into_record() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, _ = service.create_record(_request(fixture))
    serialized = json.dumps(record.to_dict())

    assert "FAKE-IBM-ACCESS-TOKEN-must-not-appear" not in serialized
    assert "FAKE-IBM-APIKEY-must-not-appear" not in serialized


def test_create_is_idempotent_and_get_returns_record() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)

    first, created_first = service.create_record(_request(fixture))
    second, created_second = service.create_record(_request(fixture))

    assert created_first is True
    assert created_second is False
    assert first.record_id == second.record_id

    fetched = service.get_provenance(first.record_id)
    assert fetched is not None
    assert fetched.record_id == first.record_id
