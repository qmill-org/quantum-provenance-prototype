"""Offline tests for the live IBM Quantum retrieval layer (fake runtime objects)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("qiskit_ibm_runtime")

from qiskit import QuantumCircuit  # noqa: E402

from qmill_quantum_provenance.integration import JobNotFoundError  # noqa: E402
from qmill_quantum_provenance.live.ibm import LiveIBMIntegration, summarize_properties  # noqa: E402
from qmill_quantum_provenance.live.validate import check_claims  # noqa: E402

CREATED = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)


class _Bits:
    def get_counts(self):
        return {"00": 498, "11": 502}


class _PubResult:
    data = {"meas": _Bits()}


class _Result(list):
    metadata = {"version": 2}


class _Job:
    creation_date = CREATED
    primitive_id = "sampler"
    session_id = None
    usage_estimation = {"quantum_seconds": 2}

    def __init__(self) -> None:
        circuit = QuantumCircuit(2, 2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure([0, 1], [0, 1])
        self.inputs = {"pubs": [(circuit, None, 1000)]}

    def job_id(self):
        return "d1abc"

    def status(self):
        return "DONE"

    def metrics(self):
        return {
            "timestamps": {
                "created": "2026-11-19T08:00:00Z",
                "running": "2026-11-19T08:05:00Z",
                "finished": "2026-11-19T08:05:04Z",
            },
            "usage": {"quantum_seconds": 2},
            "qiskit_version": "2.6.2",
        }

    def backend(self):
        return type("B", (), {"name": "ibm_aachen"})()

    def result(self):
        return _Result([_PubResult()])


class _Properties:
    def to_dict(self):
        return {
            "last_update_date": datetime(2026, 11, 19, 6, 6, tzinfo=UTC),
            "qubits": [
                [
                    {"name": "T1", "value": 100.0, "unit": "us"},
                    {"name": "readout_error", "value": 0.01},
                ],
                [
                    {"name": "T1", "value": 300.0, "unit": "us"},
                    {"name": "readout_error", "value": 0.03},
                ],
            ],
            "gates": [{"gate": "cz", "parameters": [{"name": "gate_error", "value": 0.004}]}],
        }


class _Backend:
    def __init__(self) -> None:
        self.properties_requested_at = "unset"

    def configuration(self):
        return type(
            "C",
            (),
            {
                "backend_name": "ibm_aachen",
                "backend_version": "2.0.1",
                "n_qubits": 156,
                "processor_type": {"family": "Heron", "revision": "3"},
                "basis_gates": ["cz", "rz", "sx", "x"],
                "simulator": False,
            },
        )()

    def properties(self, datetime=None):
        self.properties_requested_at = datetime
        return _Properties()

    def status(self):
        return type("S", (), {"operational": True})()


class _Service:
    def __init__(self, missing: bool = False) -> None:
        self.missing = missing
        self.backend_instance = _Backend()

    def job(self, job_id):
        if self.missing:
            raise RuntimeError("Job d1abc not found")
        return _Job()

    def backend(self, name):
        return self.backend_instance


def test_summarize_properties_names_aggregations_and_keeps_snapshot_time() -> None:
    summary = summarize_properties(_Properties().to_dict())
    assert summary["captured_at"] == "2026-11-19T06:06:00+00:00"
    assert summary["metrics"]["T1.median_over_qubits[us]"] == pytest.approx(200.0)
    assert summary["metrics"]["gate_error.cz.median"] == pytest.approx(0.004)


def test_live_ibm_maps_job_and_requests_properties_as_of_job_creation() -> None:
    service = _Service()
    live = LiveIBMIntegration(service=service)
    handle = live.get_task("d1abc")
    snapshot = live.get_status(handle)
    assert (snapshot.status, snapshot.shots, snapshot.target_id) == ("DONE", 1000, "ibm_aachen")
    assert snapshot.metadata["timestamps"]["running"] == "2026-11-19T08:05:00Z"

    device = live.get_device_details(snapshot.target_id)
    assert service.backend_instance.properties_requested_at == CREATED
    assert device.provider_properties["num_qubits"] == 156

    result = live.get_result(handle)
    assert result.measurement_counts == {"00": 498, "11": 502}
    assert result.compiled_circuit.startswith("OPENQASM 3")
    assert live.notes["measurement_counts_origin"] == "observed_samples:meas"
    assert live.notes["compiled_program_origin"] == "application_compiled_job_input"


def test_schema_v2_quantum_program_inputs_give_shots_and_circuit() -> None:
    from qmill_quantum_provenance.live.ibm import _first_circuit, _shots

    circuit = QuantumCircuit(1, 1)
    item = type("SamplexItem", (), {"circuit": circuit})()
    program = type("QuantumProgram", (), {"shots": 64, "items": [item]})()
    inputs = {"schema_version": "v2.0", "quantum_program": program, "options": object()}
    assert _shots(inputs) == 64
    assert _first_circuit(inputs) is circuit


def test_missing_ibm_job_raises_typed_not_found_error() -> None:
    live = LiveIBMIntegration(service=_Service(missing=True))
    with pytest.raises(JobNotFoundError):
        live.get_status(live.get_task("d1abc"))


def test_claim_check_flags_application_compiled_program_attributed_to_provider() -> None:
    payload = {
        "evidence": [{"path": "/artifacts/0", "status": "provider_passthrough"}],
        "artifacts": [{"role": "compiled"}],
    }
    manifest = {"notes": {"compiled_program_origin": "application_compiled_job_input"}}
    checks = {finding["check"] for finding in check_claims(payload, manifest)}
    assert "application_compiled_attributed_to_provider" in checks
