"""AC-5: upstream failures yield partial, schema-valid records (live captures)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from qmill_quantum_provenance.adapter import CreateProvenanceRecordRequest
from qmill_quantum_provenance.contract import validate_record
from qmill_quantum_provenance.evaluation import build_service

CAPTURES = Path(__file__).resolve().parents[1] / "captures"
EXPIRED = CAPTURES / "braket" / "04470467-2658-4b06-8e5c-35b841c7b054"
CANCELLED = CAPTURES / "braket" / "a55acc36-513d-448c-9d49-a543d216afd4"
COMPLETED_IBM = CAPTURES / "ibm" / "dbvb21eppgvc73e5o380"


def _record(fixture: dict) -> dict:
    service = build_service({fixture["provider"]: fixture})
    record, _ = service.create_record(
        CreateProvenanceRecordRequest(
            provider=fixture["provider"],
            external_job_id=fixture["external_job_id"],
            region=fixture.get("region"),
        )
    )
    payload = record.to_dict()
    validate_record(payload)
    return payload


def _evidence(payload: dict) -> dict[str, dict]:
    return {item["path"]: item for item in payload["evidence"]}


def _fixture(directory: Path) -> dict:
    return json.loads((directory / "fixture.json").read_text())


def test_job_the_provider_no_longer_returns_gives_a_partial_record() -> None:
    payload = _record(_fixture(EXPIRED))
    assert payload["job"]["status"] == "unknown"
    assert payload["results"] == {"available": False}
    assert _evidence(payload)["/job/status"]["reason"] == "not_found_by_provider"
    assert payload["warnings"][0]["code"] == "upstream_failure"


def test_cancelled_job_has_results_not_applicable_rather_than_failed() -> None:
    payload = _record(_fixture(CANCELLED))
    assert payload["job"]["status"] == "cancelled"
    assert _evidence(payload)["/results"]["status"] == "not_applicable"


def test_denied_result_retrieval_keeps_the_rest_of_the_record() -> None:
    fixture = copy.deepcopy(_fixture(COMPLETED_IBM))
    fixture["upstream_errors"] = {
        "get_result": {"error": "AccessDeniedError", "message": "HTTP 403"}
    }
    payload = _record(fixture)
    assert payload["job"]["status"] == "completed"
    assert payload["results"]["available"] is False
    assert _evidence(payload)["/results"]["reason"] == "authentication_scope_insufficient"


FORTE1_VIA_BRAKET = CAPTURES / "braket" / "c5f722a5-ee93-443e-8d89-f7ab285d7f69"


def test_ionq_probabilities_relayed_by_braket_are_not_presented_as_counts() -> None:
    payload = _record(_fixture(FORTE1_VIA_BRAKET))
    results = payload["results"]
    assert "measurement_counts" not in results
    assert results["outcome_basis"] == "bitstring"
    assert abs(sum(results["measurement_probabilities"].values()) - 1) < 1e-6
    evidence = _evidence(payload)
    assert evidence["/results/measurement_probabilities"]["status"] == "provider_passthrough"
    assert evidence["/results/estimated_measurement_counts"]["status"] == "derived"
    assert evidence["/results/measurement_counts"]["status"] == "not_applicable"


RIGETTI_VIA_BRAKET = CAPTURES / "braket" / "e4279728-4620-487c-9879-f302eef1ed6f"


def test_artifacts_name_their_producer_and_keep_the_original_program_digest() -> None:
    payload = _record(_fixture(RIGETTI_VIA_BRAKET))
    by_role = {artifact["role"]: artifact for artifact in payload["artifacts"]}
    assert by_role["submitted"]["producer"] == "application"
    assert by_role["compiled"]["producer"] == "provider"
    native = json.loads((RIGETTI_VIA_BRAKET / "native.json").read_text())
    placeholder = native["results_json"]["additionalMetadata"]["action"]["source"]
    assert by_role["submitted"]["content_hash"]["value"] in placeholder

    empty = _record(_fixture(FORTE1_VIA_BRAKET))
    assert "compiled" not in {a["role"] for a in empty["artifacts"]}
    assert "present but empty" in _evidence(empty)["/compilation"]["notes"]
