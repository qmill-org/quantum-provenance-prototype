"""Offline tests for the live-retrieval layer (no network, stubbed AWS session)."""

from __future__ import annotations

import io
import json

import pytest

from qmill_quantum_provenance.integration import JobNotFoundError
from qmill_quantum_provenance.live.braket import (
    LiveBraketIntegration,
    counts_from_result,
    summarize_calibration,
)
from qmill_quantum_provenance.live.capture import capture
from qmill_quantum_provenance.live.sanitize import sanitize
from qmill_quantum_provenance.live.validate import check_claims
from qmill_quantum_provenance.replay import ReplayIntegrationAdapter

ACCOUNT = "123456789012"
TASK_ARN = f"arn:aws:braket:us-east-1:{ACCOUNT}:quantum-task/abc"
DEVICE_ARN = "arn:aws:braket:us-east-1::device/qpu/ionq/Forte-1"


class _ClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _Braket:
    def __init__(self, task: dict | None) -> None:
        self._task = task

    def get_quantum_task(self, **_kwargs):
        if self._task is None:
            raise _ClientError("ResourceNotFoundException")
        return dict(self._task)

    def get_device(self, **_kwargs):
        capabilities = {
            "paradigm": {"qubitCount": 36},
            "provider": {"fidelity": {"2Q": {"mean": 0.99}}},
            "service": {"updatedAt": "2026-10-19T00:00:00+00:00"},
        }
        return {
            "deviceName": "Forte 1",
            "deviceType": "QPU",
            "deviceStatus": "ONLINE",
            "providerName": "IonQ",
            "deviceCapabilities": json.dumps(capabilities),
        }


class _S3:
    def __init__(self, result: dict) -> None:
        self._result = result

    def get_object(self, **_kwargs):
        return {"Body": io.BytesIO(json.dumps(self._result).encode())}


class _Session:
    def __init__(self, task: dict | None, result: dict) -> None:
        self._braket, self._s3 = _Braket(task), _S3(result)

    def client(self, name: str, region_name: str | None = None):
        return self._braket if name == "braket" else self._s3


_TASK = {
    "quantumTaskArn": TASK_ARN,
    "status": "COMPLETED",
    "deviceArn": DEVICE_ARN,
    "shots": 100,
    "outputS3Bucket": f"amazon-braket-us-east-1-{ACCOUNT}",
    "outputS3Directory": "tasks/abc",
}
_PROBABILITY_RESULT = {
    "measurementProbabilities": {"00": 0.504, "11": 0.496},
    "additionalMetadata": {
        "action": {"source": "OPENQASM 3.0;"},
        "ionqMetadata": {"compiledProgram": ""},
    },
}


def test_counts_distinguish_observed_from_expanded_probabilities() -> None:
    observed, origin = counts_from_result({"measurements": [[0, 0], [1, 1], [0, 0]]}, 3)
    assert (observed, origin) == ({"00": 2, "11": 1}, "observed_measurements")
    expanded, origin = counts_from_result({"measurementProbabilities": {"0": 0.25}}, 10)
    assert (expanded, origin) == ({"0": 2}, "expanded_from_measurementProbabilities")


def test_service_document_timestamp_is_not_a_characterization_timestamp() -> None:
    summary = summarize_calibration(
        {
            "service": {"updatedAt": "2026-11-15T00:00:00+00:00"},
            "standardized": {
                "oneQubitProperties": {
                    "0": {"T1": {"value": 2e-5, "unit": "S"}, "oneQubitFidelity": []},
                    "1": {"T1": {"value": 4e-5, "unit": "S"}, "oneQubitFidelity": []},
                }
            },
        }
    )
    assert summary["captured_at"] is None
    assert summary["service_updated_at"] == "2026-11-15T00:00:00+00:00"
    assert summary["metrics"]["standardized.T1[S].median_over_qubits"] == pytest.approx(3e-5)


def test_sanitize_masks_account_ids_secrets_and_program_text() -> None:
    cleaned = sanitize(
        {
            "arn": TASK_ARN,
            "sessionToken": "s",
            "bucket": _TASK["outputS3Bucket"],
            "action": {"source": "OPENQASM 3.0; secret_algorithm;"},
            "ionqMetadata": {"compiledProgram": ""},
            "session": {"user_id": "iam-ServiceId-844e473a-0b26-46f5-8483"},
        }
    )
    text = json.dumps(cleaned)
    assert ACCOUNT not in text
    assert cleaned["session"]["user_id"] == "iam-ServiceId-<masked>"
    assert '"s"' not in text
    assert "secret_algorithm" not in text
    assert cleaned["action"]["source"].startswith("<program redacted sha256=")
    assert cleaned["ionqMetadata"]["compiledProgram"] == ""


def test_live_braket_maps_probability_only_results_and_records_origin() -> None:
    live = LiveBraketIntegration(session=_Session(_TASK, _PROBABILITY_RESULT))
    handle = live.get_task(TASK_ARN)
    assert handle.region == "us-east-1"
    result = live.get_result(handle)
    assert result.measurement_counts == {"00": 50, "11": 50}
    assert live.notes == {
        "measurement_counts_origin": "expanded_from_measurementProbabilities",
        "submitted_program_available": True,
        "compiled_program": "present_empty",
    }


def test_missing_task_raises_typed_not_found_error() -> None:
    live = LiveBraketIntegration(session=_Session(None, {}))
    with pytest.raises(JobNotFoundError):
        live.get_status(live.get_task(TASK_ARN))


def test_captured_upstream_error_replays_as_the_same_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "qmill_quantum_provenance.live.capture._integration",
        lambda _provider: LiveBraketIntegration(session=_Session(None, {})),
    )
    bundle = capture("braket", TASK_ARN)
    assert ACCOUNT not in json.dumps(bundle)
    replay = ReplayIntegrationAdapter(bundle["fixture"])
    with pytest.raises(JobNotFoundError):
        replay.get_status(replay.get_task(TASK_ARN))


def test_claim_checks_flag_mislabelled_counts_and_unmapped_submitted_program() -> None:
    payload = {
        "evidence": [{"path": "/results/measurement_counts", "status": "provider_supplied"}],
        "artifacts": [],
        "job": {"ended_at": "2026-08-31T00:00:00+00:00"},
        "characterization": {
            "association": "current_at_retrieval",
            "captured_at": "2026-10-19T00:00:00+00:00",
        },
    }
    manifest = {
        "notes": {
            "measurement_counts_origin": "expanded_from_measurementProbabilities",
            "submitted_program_available": True,
        }
    }
    checks = {finding["check"] for finding in check_claims(payload, manifest)}
    assert checks == {
        "derived_counts_labeled_provider_supplied",
        "submitted_program_not_mapped",
        "characterization_postdates_job",
    }


def test_analog_shots_use_the_sdk_site_convention_and_unknown_layouts_are_not_tallied() -> None:
    from qmill_quantum_provenance.live.braket import counts_from_result

    shot = {
        "shotMetadata": {"shotStatus": "Success"},
        "shotResult": {"preSequence": [1, 1, 0], "postSequence": [0, 1, 0]},
    }
    failed = {"shotMetadata": {"shotStatus": "Failure"}, "shotResult": {}}
    counts, origin = counts_from_result({"measurements": [shot, shot, failed]}, 3)
    assert (counts, origin) == ({"rge": 2}, "observed_ahs_site_states")
    counts, origin = counts_from_result({"measurements": [{"bits": "01"}]}, 1)
    assert (counts, origin) == ({}, "unrecognized_shot_format")
