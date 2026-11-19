"""Tests for the Quandela live layer (fake handler) and adapter (captured fixture)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pcvl = pytest.importorskip("perceval")

from perceval.serialization import serialize  # noqa: E402

from qmill_quantum_provenance.adapter import CreateProvenanceRecordRequest  # noqa: E402
from qmill_quantum_provenance.contract import validate_record  # noqa: E402
from qmill_quantum_provenance.evaluation import build_service  # noqa: E402
from qmill_quantum_provenance.live.quandela import LiveQuandelaIntegration, split_reference  # noqa: E402

CAPTURE = (
    Path(__file__).resolve().parents[1]
    / "captures"
    / "quandela"
    / "5614c93a-8d77-43f0-81c6-7a13a935255e"
)


class _Handler:
    def get_job_status(self, job_id):
        return {
            "status": "completed",
            "creation_datetime": 1795078368.6,
            "start_time": 1795078380.4,
            "duration": 17,
            "shots": 33533,
        }

    def get_job_results(self, job_id):
        counts = pcvl.BSCount({pcvl.BasicState([2, 0]): 485, pcvl.BasicState([1, 1]): 48})
        inner = {
            "results": serialize(counts),
            "physical_perf": 0.0036,
            "computed_experiment": serialize(pcvl.Experiment(24)),
        }
        return {"job_id": job_id, "results": json.dumps(inner), "shots": 33533, "duration": 17}

    def fetch_platform_details(self):
        return {
            "type": "simulator",
            "status": "available",
            "perfs": {},
            "specs": {"detector": "threshold"},
        }


def test_reference_must_name_the_platform() -> None:
    assert split_reference("sim:belenos/abc") == ("sim:belenos", "abc")
    with pytest.raises(ValueError):
        split_reference("abc")


def test_live_quandela_keeps_fock_states_shots_and_compiled_experiment() -> None:
    live = LiveQuandelaIntegration(handler_factory=lambda platform: _Handler())
    handle = live.get_task("sim:belenos/abc")
    snapshot = live.get_status(handle)
    assert (snapshot.target_id, snapshot.shots) == ("sim:belenos", 33533)
    result = live.get_result(handle)
    assert result.measurement_counts == {"|2,0>": 485, "|1,1>": 48}
    assert result.compiled_circuit_metrics == {"modes": 24}
    assert live.notes["platform_source"] == "application_reference"


def test_adapter_record_from_capture_is_valid_and_uses_extensions() -> None:
    fixture = json.loads((CAPTURE / "fixture.json").read_text())
    service = build_service({"quandela": fixture})
    record, _ = service.create_record(
        CreateProvenanceRecordRequest(
            provider="quandela", external_job_id=fixture["external_job_id"]
        )
    )
    payload = record.to_dict()
    validate_record(payload)
    assert payload["results"]["outcome_basis"] == "fock_state"
    assert "photonic.quandela" in payload["extensions"]
    statuses = {e["path"]: e["status"] for e in payload["evidence"]}
    assert statuses["/device/identifier"] == "application_captured"
    assert statuses["/device/qubit_count"] == "not_applicable"
