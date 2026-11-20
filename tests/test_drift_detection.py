"""AC-6: provider interface drift is detected, not silently degraded (live captures)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from qmill_quantum_provenance.adapter import CreateProvenanceRecordRequest
from qmill_quantum_provenance.contract import validate_record
from qmill_quantum_provenance.evaluation import build_service, load_inventory
from qmill_quantum_provenance.live.validate import check_claims, validate_capture
from qmill_quantum_provenance.models import normalize_job_status

CAPTURES = Path(__file__).resolve().parents[1] / "captures"
IONQ_V04 = CAPTURES / "ionq" / "01a1f2eb-d155-7632-bc4e-f340de096f01"
IBM_SAMPLER = CAPTURES / "ibm" / "dbvb21eppgvc73e5o380"

# Known adapter gaps the validator must keep reporting until they are closed.
KNOWN_FINDINGS: dict[str, list[str]] = {}


def _record(fixture: dict) -> dict:
    service = build_service({fixture["provider"]: fixture})
    record, _ = service.create_record(
        CreateProvenanceRecordRequest(
            provider=fixture["provider"], external_job_id=fixture["external_job_id"]
        )
    )
    payload = record.to_dict()
    validate_record(payload)
    return payload


def _fixture(directory: Path) -> dict:
    return json.loads((directory / "fixture.json").read_text())


def _evidence(payload: dict) -> dict[str, dict]:
    return {item["path"]: item for item in payload["evidence"]}


def _codes(payload: dict) -> list[str]:
    return [warning["code"] for warning in payload["warnings"]]


def _rename(fixture: dict, old: str, new: str, value=None) -> dict:
    fixture = copy.deepcopy(fixture)
    metadata = fixture["snapshot"]["metadata"]
    current = metadata.pop(old)
    metadata[new] = current if value is None else value
    return fixture


def test_ionq_run_duration_is_read_under_both_api_versions() -> None:
    v04 = _record(_fixture(IONQ_V04))
    assert v04["execution"]["run_duration_ms"] == 0
    evidence = _evidence(v04)["/execution/run_duration_ms"]
    assert evidence["provider_field"].endswith("execution_duration_ms")

    v03 = _record(_rename(_fixture(IONQ_V04), "execution_duration_ms", "execution_time_ms", 1234))
    assert v03["execution"]["run_duration_ms"] == 1234
    assert _evidence(v03)["/execution/run_duration_ms"]["provider_field"].endswith(
        "execution_time_ms"
    )
    assert "expected_provider_field_missing" not in _codes(v03)


def test_an_unknown_rename_is_reported_as_drift_not_silently_unavailable() -> None:
    payload = _record(_rename(_fixture(IONQ_V04), "execution_duration_ms", "execution_runtime_ms"))
    assert "run_duration_ms" not in (payload.get("execution") or {})
    assert "expected_provider_field_missing" in _codes(payload)
    checks = [finding["check"] for finding in check_claims(payload, {})]
    assert checks == ["provider_interface_drift"]


def test_a_null_field_is_a_provider_answer_not_drift() -> None:
    fixture = copy.deepcopy(_fixture(IONQ_V04))
    fixture["snapshot"]["metadata"]["execution_duration_ms"] = None
    assert "expected_provider_field_missing" not in _codes(_record(fixture))


def test_unknown_ibm_input_schema_is_flagged() -> None:
    fixture = copy.deepcopy(_fixture(IBM_SAMPLER))
    assert fixture["snapshot"]["metadata"]["input_schema"] == "v2.0"
    assert not _codes(_record(fixture))
    fixture["snapshot"]["metadata"]["input_schema"] = "v3.0"
    assert "unrecognized_provider_schema" in _codes(_record(fixture))


@pytest.mark.parametrize(
    "directory",
    sorted(path.parent for path in CAPTURES.glob("*/*/fixture.json")),
    ids=lambda path: f"{path.parent.name}/{path.name[:8]}",
)
def test_live_capture_conformance(directory: Path) -> None:
    """Every real capture yields a schema-valid record with no unexplained findings."""

    entry = validate_capture(directory, load_inventory())
    assert entry.get("schema_valid") is True
    assert [f["check"] for f in entry["findings"]] == KNOWN_FINDINGS.get(directory.name, [])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("waiting", "queued"),
        ("ready", "queued"),
        ("submitted", "created"),
        ("started", "running"),
        ("SUCCESS", "completed"),
        ("INITIALIZING", "created"),
    ],
)
def test_provider_queue_and_run_states_are_normalized(raw: str, expected: str) -> None:
    assert normalize_job_status(raw) == expected


def test_an_unknown_provider_status_is_reported_as_drift() -> None:
    fixture = copy.deepcopy(_fixture(IONQ_V04))
    fixture["snapshot"]["status"] = "paused"
    payload = _record(fixture)
    assert payload["job"]["status"] == "unknown"
    assert "unrecognized_provider_status" in _codes(payload)
    assert not _codes(_record(_fixture(IONQ_V04)))
