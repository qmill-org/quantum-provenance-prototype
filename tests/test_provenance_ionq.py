"""End-to-end IonQ provenance flow over sanitized fixtures.

Covers schema validation, IonQ-specific mapping (provider probability histogram
preserved verbatim as measurement_probabilities with derived estimated counts,
provider-linked characterization, and a provider-supplied run duration with a
derived total), a partial record (characterization unavailable and run duration
absent), redaction, and idempotent create/get semantics for the in-process
service.
"""

from __future__ import annotations

import json
from pathlib import Path

from qmill_quantum_provenance import (
    CreateProvenanceRecordRequest,
    ProvenanceService,
)
from qmill_quantum_provenance.adapters.ionq import (
    IonQProvenanceAdapter,
)
from qmill_quantum_provenance.contract import validate_record
from qmill_quantum_provenance.registry import (
    ProvenanceAdapterRegistry,
)
from qmill_quantum_provenance.replay import ReplayIntegrationAdapter

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ionq"


def _load(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def _service(fixture: dict) -> ProvenanceService:
    registry = ProvenanceAdapterRegistry()
    registry.register(
        "ionq",
        lambda: IonQProvenanceAdapter(ReplayIntegrationAdapter(fixture)),
    )
    return ProvenanceService(registry=registry)


def _request(fixture: dict, **kwargs) -> CreateProvenanceRecordRequest:
    return CreateProvenanceRecordRequest(
        provider="ionq",
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


def test_ionq_mapping_normalizes_expected_fields() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, _ = service.create_record(_request(fixture))
    payload = record.to_dict()
    validate_record(payload)

    assert record.job.status == "completed"
    assert record.job.shots == 1000
    assert record.device.type == "qpu"
    assert record.device.qubit_count == 25

    # IonQ operates its own hardware, so platform and hardware provider agree.
    assert record.device.platform_provider == "ionq"
    assert record.device.hardware_provider == "ionq"

    # IonQ-specific: the provider probability histogram is preserved verbatim as
    # measurement_probabilities (integer basis states rewritten as fixed-width
    # bitstrings). Observed integer counts are NOT fabricated: measurement_counts
    # is absent, and estimated_measurement_counts is a documented derivation.
    assert record.results.available is True
    assert record.results.measurement_counts is None
    assert record.results.measurement_probabilities == {"00000": 0.492, "11111": 0.508}
    assert record.results.estimated_measurement_counts == {"00000": 492, "11111": 508}

    # IonQ-specific: run duration is provider-supplied, total is derived.
    # created 12:00:00 -> ended 12:00:03.5 (total 3500 ms); run 2200 ms.
    assert record.execution is not None
    assert record.execution.run_duration_ms == 2200
    assert record.execution.total_duration_ms == 3500
    assert record.execution.queue_duration_ms is None

    # IonQ-specific: characterization is provider-linked with typed metrics.
    assert record.characterization is not None
    assert record.characterization.association.value == "provider_linked"
    assert record.characterization.metrics is not None
    metric_names = {m.name for m in record.characterization.metrics}
    assert {"mean_fidelity_1q", "mean_fidelity_2q", "t1_us"} <= metric_names
    t1 = next(m for m in record.characterization.metrics if m.name == "t1_us")
    assert t1.unit == "microseconds"
    fidelity = next(m for m in record.characterization.metrics if m.name == "mean_fidelity_1q")
    assert fidelity.unit is None

    statuses = {(e.path, e.status.value) for e in record.evidence}
    assert ("/results/measurement_probabilities", "provider_supplied") in statuses
    assert ("/results/estimated_measurement_counts", "derived") in statuses
    assert ("/results/measurement_counts", "derived") not in statuses
    assert ("/execution/run_duration_ms", "provider_supplied") in statuses
    assert ("/execution/total_duration_ms", "derived") in statuses
    assert ("/characterization", "provider_supplied") in statuses

    # Native circuit + provider-native artifacts are hash-only passthrough.
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

    # No provider execution_time -> only the total duration is derived.
    assert record.execution is not None
    assert record.execution.run_duration_ms is None
    assert record.execution.total_duration_ms == 9000

    # Histogram still preserved as probabilities for a 3-qubit register, with
    # derived estimated counts.
    assert record.results.measurement_counts is None
    assert record.results.measurement_probabilities == {"000": 0.5, "111": 0.5}
    assert record.results.estimated_measurement_counts == {"000": 250, "111": 250}


def test_no_secret_material_leaks_into_record() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, _ = service.create_record(_request(fixture))
    serialized = json.dumps(record.to_dict())

    assert "FAKE-IONQ-APIKEY-must-not-appear" not in serialized
    assert "FAKE-IONQ-BEARER-must-not-appear" not in serialized


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
