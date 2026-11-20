"""AC-7: requested vs executed shots, and expectation-value results (live captures)."""

from __future__ import annotations

import json
from pathlib import Path

from qmill_quantum_provenance.adapter import CreateProvenanceRecordRequest
from qmill_quantum_provenance.contract import validate_record
from qmill_quantum_provenance.evaluation import build_service

CAPTURES = Path(__file__).resolve().parents[1] / "captures"
IBM_ESTIMATOR = CAPTURES / "ibm" / "dbvb21mppgvc73e5o390"
IBM_SAMPLER = CAPTURES / "ibm" / "dbvb21eppgvc73e5o380"
QUANDELA_HOM = CAPTURES / "quandela" / "5614c93a-8d77-43f0-81c6-7a13a935255e"
IONQ_IDEAL = CAPTURES / "ionq" / "01a1f2eb-cee6-715d-b36e-478c679f0819"
BRAKET_RIGETTI = CAPTURES / "braket" / "8110d507-c11a-4473-88e0-0dfa04c468ec"
BRAKET_IONQ = CAPTURES / "braket" / "c5f722a5-ee93-443e-8d89-f7ab285d7f69"


def _record(directory: Path, **request) -> dict:
    fixture = json.loads((directory / "fixture.json").read_text())
    service = build_service({fixture["provider"]: fixture})
    record, _ = service.create_record(
        CreateProvenanceRecordRequest(
            provider=fixture["provider"],
            external_job_id=fixture["external_job_id"],
            region=fixture.get("region"),
            **request,
        )
    )
    payload = record.to_dict()
    validate_record(payload)
    return payload


def _evidence(payload: dict) -> dict[str, dict]:
    return {item["path"]: item for item in payload["evidence"]}


def test_estimator_expectation_values_are_a_derived_result_not_a_failure() -> None:
    payload = _record(IBM_ESTIMATOR)
    assert payload["results"]["available"] is True
    estimator = payload["extensions"]["gate_model.ibm"]["estimator"]
    assert estimator["evs"] > 0.9 and estimator["resilience_level"] == 1
    results = _evidence(payload)["/results"]
    assert results["status"] == "derived"
    assert "ClientSideEstimatorDecoder" in results["derivation"]
    assert not payload["warnings"]


def test_ibm_requested_and_executed_shots_are_kept_apart() -> None:
    estimator = _record(IBM_ESTIMATOR)
    assert estimator["job"]["shots"] == 1000
    assert estimator["execution"]["executed_shots"] == 2048  # 2 items x 16 x 64
    sampler = _record(IBM_SAMPLER)
    assert (sampler["job"]["shots"], sampler["execution"]["executed_shots"]) == (1000, 1000)


def test_photon_detections_are_executed_shots_and_the_request_comes_from_the_application() -> None:
    payload = _record(QUANDELA_HOM)
    assert "shots" not in payload["job"]
    assert _evidence(payload)["/job/shots"]["status"] == "unavailable"
    assert payload["execution"]["executed_shots"] == 33533
    assert _evidence(payload)["/execution/executed_shots"]["status"] == "provider_supplied"

    captured = _record(QUANDELA_HOM, requested_shots=1000)
    assert captured["job"]["shots"] == 1000
    assert _evidence(captured)["/job/shots"]["status"] == "application_captured"


def test_ideal_simulation_executes_no_shots() -> None:
    payload = _record(IONQ_IDEAL, requested_shots=1000)
    assert _evidence(payload)["/execution/executed_shots"]["status"] == "not_applicable"
    assert _evidence(payload)["/job/shots"]["status"] == "application_captured"


def test_disagreeing_request_is_warned_and_the_provider_value_kept() -> None:
    payload = _record(IBM_SAMPLER, requested_shots=500)
    assert payload["job"]["shots"] == 1000
    assert [w["code"] for w in payload["warnings"]] == ["shots_mismatch"]


def test_braket_executed_shots_come_from_per_shot_measurements_only() -> None:
    rigetti = _record(BRAKET_RIGETTI)
    assert rigetti["execution"]["executed_shots"] == 1000
    assert _evidence(rigetti)["/execution/executed_shots"]["status"] == "derived"
    relayed = _record(BRAKET_IONQ)
    assert "executed_shots" not in (relayed.get("execution") or {})
    assert _evidence(relayed)["/execution/executed_shots"]["status"] == "unavailable"


IONQ_NOISY = CAPTURES / "ionq" / "01a1f2eb-d155-7632-bc4e-f340de096f01"


def test_simulator_noise_model_and_seed_go_to_the_simulation_extension() -> None:
    noisy = _record(IONQ_NOISY)
    simulation = noisy["extensions"]["simulation.ionq"]
    assert simulation["noise_model"] == "forte-1" and isinstance(simulation["seed"], int)
    assert _evidence(noisy)["/extensions/simulation.ionq"]["status"] == "provider_supplied"
    ideal = _record(IONQ_IDEAL)
    assert ideal["extensions"]["simulation.ionq"] == {"noise_model": "ideal"}
