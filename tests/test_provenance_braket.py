"""End-to-end Braket provenance flow over sanitized fixtures.

Covers schema validation, provider mapping, a partial record (characterization
unavailable), provider-branching isolation, redaction, and idempotent
create/get semantics for the in-process service.
"""

from __future__ import annotations

import json
from pathlib import Path

from qmill_quantum_provenance import (
    ApplicationCompilationContext,
    ApplicationSoftwareContext,
    CreateProvenanceRecordRequest,
    ProvenanceService,
    SourceProgramInput,
)
from qmill_quantum_provenance.adapter import (
    AdapterResult,
    ProvenanceAdapter,
    ProvenanceCollectionRequest,
)
from qmill_quantum_provenance.adapters.braket import (
    BraketProvenanceAdapter,
)
from qmill_quantum_provenance.contract import validate_record
from qmill_quantum_provenance.models import (
    Device,
    Job,
    Results,
)
from qmill_quantum_provenance.redaction import find_secret_keys, redact
from qmill_quantum_provenance.registry import (
    ProvenanceAdapterRegistry,
)
from qmill_quantum_provenance.replay import ReplayIntegrationAdapter

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "braket"


def _load(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def _service(fixture: dict) -> ProvenanceService:
    registry = ProvenanceAdapterRegistry()
    registry.register(
        "braket",
        lambda: BraketProvenanceAdapter(ReplayIntegrationAdapter(fixture)),
    )
    return ProvenanceService(registry=registry)


def _request(fixture: dict, **kwargs) -> CreateProvenanceRecordRequest:
    return CreateProvenanceRecordRequest(
        provider="braket",
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


def test_braket_mapping_normalizes_expected_fields() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, _ = service.create_record(
        _request(
            fixture,
            source_program=SourceProgramInput(
                format="openqasm3",
                reference="s3://app-bucket/programs/bell.qasm",
                content_hash=("sha256", "abc123"),
            ),
            software_context=ApplicationSoftwareContext(
                provider_client="amazon-braket-sdk",
                provider_client_version="1.90.0",
                python_version="3.12.12",
                framework_versions={"qiskit": "2.3.0"},
            ),
            compilation_context=ApplicationCompilationContext(
                compiler_name="qiskit-transpiler",
                optimization_level=3,
                logical_to_physical_mapping=[(0, 14), (1, 15)],
            ),
        )
    )
    payload = record.to_dict()
    validate_record(payload)

    assert record.job.status == "completed"
    assert record.job.shots == 1000
    assert record.device.type == "qpu"
    assert record.device.qubit_count == 25
    # Braket is an aggregation platform: the platform and the underlying hardware
    # operator (parsed from the device ARN) are distinct and both preserved.
    assert record.device.platform_provider == "amazon_braket"
    assert record.device.hardware_provider == "ionq"
    assert record.results.available is True
    assert record.results.measurement_counts == {"00": 511, "11": 489}

    # Derived execution timing: 10:00:00 -> 10:00:03.5 == 3500 ms.
    assert record.execution is not None
    assert record.execution.total_duration_ms == 3500

    # Provider characterization snapshot present.
    assert record.characterization is not None
    assert record.characterization.metrics is not None
    assert len(record.characterization.metrics) == 2

    # Application-captured context merged and marked.
    assert record.software is not None
    assert record.software.provider_client == "amazon-braket-sdk"
    assert record.compilation is not None
    assert record.compilation.logical_to_physical_mapping is not None

    statuses = {(e.path, e.status.value) for e in record.evidence}
    assert ("/job/status", "provider_supplied") in statuses
    assert ("/execution/total_duration_ms", "derived") in statuses
    assert ("/characterization", "provider_supplied") in statuses
    assert any(
        path.startswith("/software/") and status == "application_captured"
        for path, status in statuses
    )
    assert any(
        path.startswith("/compilation/") and status == "application_captured"
        for path, status in statuses
    )

    # Compiled + provider-native artifacts are hash-only passthrough.
    roles = {artifact.role.value for artifact in record.artifacts}
    assert "compiled" in roles
    assert "provider_native" in roles
    assert "source" in roles


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


def test_no_secret_material_leaks_into_record() -> None:
    fixture = _load("completed.json")
    service = _service(fixture)
    record, _ = service.create_record(_request(fixture))
    serialized = json.dumps(record.to_dict())

    assert "FAKE-SESSION-TOKEN-must-not-appear" not in serialized
    assert "FAKE-SECRET-must-not-appear" not in serialized


def test_redaction_masks_secret_keys() -> None:
    payload = {
        "deviceArn": "arn:aws:braket:...",
        "sessionToken": "super-secret",
        "nested": {"aws_secret_access_key": "leak", "shots": 1000},
    }
    redacted = redact(payload)

    assert redacted["deviceArn"] == "arn:aws:braket:..."
    assert redacted["sessionToken"] != "super-secret"
    assert redacted["nested"]["aws_secret_access_key"] != "leak"
    assert redacted["nested"]["shots"] == 1000
    assert find_secret_keys(redacted)  # keys remain, values masked


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
    assert service.get_provenance("qprov:braket:does-not-exist") is None


def test_provider_branching_is_isolated_to_adapter() -> None:
    """The service performs identical assembly regardless of provider.

    A minimal second adapter flows through the same service without any
    Braket-specific behavior leaking in, demonstrating that provider logic is
    confined to adapters (change-isolation for the shared client).
    """

    class _DummyAdapter(ProvenanceAdapter):
        provider = "dummy"
        name = "dummy-adapter"
        version = "0.0.0"

        def capabilities(self):  # pragma: no cover - trivial
            from qmill_quantum_provenance.adapter import (
                AdapterCapabilities,
            )

            return AdapterCapabilities(provider="dummy")

        def collect(self, request: ProvenanceCollectionRequest) -> AdapterResult:
            return AdapterResult(
                job=Job(
                    canonical_id=request.canonical_id,
                    provider="dummy",
                    external_id=request.external_job_id,
                    status="completed",
                ),
                device=Device(provider="dummy", identifier="dummy-device"),
                results=Results(available=False),
            )

    registry = ProvenanceAdapterRegistry()
    registry.register("dummy", _DummyAdapter)
    service = ProvenanceService(registry=registry)

    record, _ = service.create_record(
        CreateProvenanceRecordRequest(provider="dummy", external_job_id="job-1")
    )
    payload = record.to_dict()

    validate_record(payload)
    assert payload["device"]["provider"] == "dummy"
    assert payload["adapter"]["provider"] == "dummy"
    # QMill-level operation accounting is added by the shared service, not the adapter.
    assert any(op["actor"] == "qmill" for op in payload["operations"])
