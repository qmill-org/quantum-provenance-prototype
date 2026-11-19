"""Offline tests for the live IonQ retrieval layer (fake HTTP client)."""

from __future__ import annotations

import pytest

from qmill_quantum_provenance.integration import (
    JobNotFoundError,
    ResultUnavailableError,
    TaskHandle,
)
from qmill_quantum_provenance.live.ionq import LiveIonQIntegration

JOB = {
    "id": "j1",
    "status": "completed",
    "backend": "qpu.forte-1",
    "submitted_at": "2026-11-19T08:28:22Z",
    "completed_at": "2026-11-19T08:30:00Z",
    "shots": 1000,
    "execution_duration_ms": 4200,
    "session_id": "s1",
    "stats": {"qubits": 2},
    "output": {"compilation": {"compiled_circuits": {"ionq.qasm3.v1": {"id": "a1"}}}},
}
ROUTES = {
    "/jobs/j1": JOB,
    "/jobs/j1/results/probabilities": {"0": 0.5, "3": 0.5},
    "/jobs/j1/artifacts/a1": "OPENQASM 3.0;",
    "/backends/qpu.forte-1": {"backend": "qpu.forte-1", "qubits": 36, "characterization_id": "now"},
    "/backends/qpu.forte-1/characterizations": {
        "characterizations": [
            {"id": "c-1118", "date": "2026-11-18T00:00:00Z", "fidelity": {"2q": {"median": 0.993}}}
        ]
    },
}


class _Response:
    def __init__(self, body):
        self.status_code = 404 if body is None else 200
        self._body = body
        self.text = body if isinstance(body, str) else ""

    def json(self):
        return self._body


class _Client:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return _Response(self.routes.get(path))


def test_ionq_job_fields_pass_through_and_probabilities_stay_probabilities() -> None:
    live = LiveIonQIntegration(client=_Client(ROUTES))
    handle = live.get_task("j1")
    snapshot = live.get_status(handle)
    assert snapshot.metadata["execution_duration_ms"] == 4200
    assert "execution_time_ms" not in snapshot.metadata
    assert snapshot.metadata["session_id"] == "s1"
    result = live.get_result(handle)
    assert result.measurement_counts == {}
    assert result.raw_payload["histogram"] == {"0": 0.5, "3": 0.5}
    assert result.compiled_circuit == "OPENQASM 3.0;"
    assert live.notes["compiled_program_origin"] == "provider_compiled_artifact"


def test_qpu_characterization_is_the_latest_at_or_before_submission() -> None:
    client = _Client(ROUTES)
    live = LiveIonQIntegration(client=client)
    live.get_status(live.get_task("j1"))
    device = live.get_device_details("qpu.forte-1")
    assert (
        "/backends/qpu.forte-1/characterizations",
        {"end": JOB["submitted_at"], "limit": 1},
    ) in client.calls
    assert device.calibration_data["characterization_id"] == "c-1118"
    assert device.calibration_data["metrics"] == {"fidelity.2q.median": 0.993}


def test_failed_job_has_no_result_and_missing_job_is_not_found() -> None:
    failed = dict(JOB, status="failed", failure={"code": "BadGate"})
    live = LiveIonQIntegration(client=_Client({**ROUTES, "/jobs/j1": failed}))
    with pytest.raises(ResultUnavailableError, match="BadGate"):
        live.get_result(live.get_task("j1"))
    with pytest.raises(JobNotFoundError):
        LiveIonQIntegration(client=_Client({})).get_status(
            TaskHandle(provider="ionq", provider_job_id="missing")
        )
