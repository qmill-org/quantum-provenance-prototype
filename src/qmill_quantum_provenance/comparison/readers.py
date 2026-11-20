"""Answer the protocol's questions from a record alone.

``read_baseline`` uses only field names of the flat record (arm B).
``read_contract`` uses the documented meaning of contract fields, evidence and
association states (arms V1 and V2; V2 fields are simply absent in V1).
A reader answers ``UNDETERMINABLE`` when the record does not allow an answer.
Both readers share two deductions any consumer can make: a cancelled or failed
job did not run, and a characterization timestamp can be compared with the
job's times.
"""

from __future__ import annotations

from typing import Any

from .oracle import parse_time, time_relation

UNDETERMINABLE = "undeterminable"
_NOT_RUN = {"cancelled", "canceled", "failed", "error"}
_PENDING = {"created", "queued", "running", "waiting", "ready", "submitted", "initializing"}
_PROVIDER_STATES = {"provider_supplied", "provider_passthrough", "aggregator_normalized"}


def _times(created: Any, ended: Any) -> list[str | None]:
    parsed = [parse_time(created), parse_time(ended)]
    return [value.isoformat() if value else None for value in parsed]


def read_baseline(record: dict[str, Any]) -> dict[str, Any]:
    status = str(record.get("status") or "")
    not_run, pending = status in _NOT_RUN, status in _PENDING
    answers: dict[str, Any] = {"Q0": True}
    # Q1: a field named counts reads as observed counts.
    answers["Q1"] = "observed_counts" if record.get("counts") else UNDETERMINABLE
    # Q2: a compiled circuit retrieved from the provider reads as the provider's.
    answers["Q2"] = "provider" if record.get("compiled_circuit") else UNDETERMINABLE
    if not record.get("calibration"):
        answers["Q3"] = UNDETERMINABLE
    elif not_run:
        answers["Q3"] = "no_execution"
    else:
        answers["Q3"] = time_relation(
            parse_time(record.get("last_calibrated")),
            parse_time(record.get("created_at")),
            parse_time(record.get("ended_at")),
        )
    # Q4 (face value): the provider field names the operator.
    answers["Q4"] = record.get("provider") or UNDETERMINABLE
    if record.get("counts"):
        answers["Q5"] = UNDETERMINABLE
    else:
        answers["Q5"] = "did_not_run" if not_run else "not_yet" if pending else UNDETERMINABLE
    shots = record.get("shots")
    answers["Q6"] = shots if shots is not None else UNDETERMINABLE
    answers["Q7"] = shots if shots is not None else UNDETERMINABLE
    answers["Q8"] = UNDETERMINABLE
    answers["Q9"] = UNDETERMINABLE
    answers["Q10"] = UNDETERMINABLE
    answers["Q11"] = record.get("counts") or UNDETERMINABLE
    answers["N1"] = record.get("qpu_name") or UNDETERMINABLE
    answers["N2"] = _times(record.get("created_at"), record.get("ended_at"))
    answers["N3"] = record.get("qubit_count") or UNDETERMINABLE
    return answers


def read_contract(record: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {}
    for item in record.get("evidence") or []:
        evidence.setdefault(item["path"], item)
    job = record.get("job") or {}
    status = str(job.get("status") or "")
    not_run, pending = status in _NOT_RUN, status in _PENDING
    results = record.get("results") or {}
    result_evidence = evidence.get("/results") or {}
    answers: dict[str, Any] = {"Q0": True}

    if results.get("available"):
        if result_evidence.get("status") == "derived":
            answers["Q1"] = "client_derived"
        elif results.get("measurement_counts"):
            counts_evidence = evidence.get("/results/measurement_counts") or {}
            answers["Q1"] = (
                "client_derived"
                if counts_evidence.get("status") == "derived"
                else "observed_counts"
            )
        elif results.get("measurement_probabilities"):
            answers["Q1"] = "probabilities"
        else:
            answers["Q1"] = UNDETERMINABLE
    elif status == "completed" and result_evidence.get("reason") == "upstream_request_failed":
        answers["Q1"] = "retrieval_failed"
    else:
        answers["Q1"] = UNDETERMINABLE

    answers["Q2"] = _program_producer(record, evidence)

    characterization = record.get("characterization") or {}
    if (evidence.get("/characterization") or {}).get("status") == "not_applicable" or (
        characterization and not_run
    ):
        answers["Q3"] = "no_execution"
    elif not characterization:
        answers["Q3"] = UNDETERMINABLE
    elif characterization.get("captured_at"):
        answers["Q3"] = time_relation(
            parse_time(characterization["captured_at"]),
            parse_time(job.get("created_at")),
            parse_time(job.get("ended_at")),
        )
    elif characterization.get("association") == "provider_linked":
        answers["Q3"] = "matched"
    else:
        answers["Q3"] = "unknown_time"

    operator = (record.get("device") or {}).get("hardware_provider")
    answers["Q4"] = operator or UNDETERMINABLE

    if results.get("available"):
        answers["Q5"] = UNDETERMINABLE
    elif result_evidence.get("status") == "not_applicable" or not_run:
        answers["Q5"] = "did_not_run"
    elif result_evidence.get("reason") == "not_found_by_provider":
        answers["Q5"] = "not_retrievable"
    elif pending:
        answers["Q5"] = "not_yet"
    elif status == "completed" and result_evidence.get("reason") == "upstream_request_failed":
        answers["Q5"] = "retrieval_failed"
    else:
        answers["Q5"] = UNDETERMINABLE

    shots = job.get("shots")
    answers["Q6"] = shots if shots is not None else UNDETERMINABLE
    execution = record.get("execution") or {}
    executed_evidence = evidence.get("/execution/executed_shots")
    if execution.get("executed_shots") is not None:
        answers["Q7"] = execution["executed_shots"]
    elif executed_evidence and executed_evidence.get("status") == "not_applicable":
        answers["Q7"] = "none"
    elif executed_evidence is None:
        # A contract with one shots field answers both questions with it.
        answers["Q7"] = shots if shots is not None else UNDETERMINABLE
    else:
        answers["Q7"] = UNDETERMINABLE

    relations = job.get("relations") or {}
    relation_status = (evidence.get("/job/relations") or {}).get("status")
    if relations.get("batch_id"):
        answers["Q8"] = f"batch:{relations['batch_id']}"
    elif relations.get("session_id"):
        answers["Q8"] = f"session:{relations['session_id']}"
    elif relations.get("parent_job_id"):
        answers["Q8"] = f"parent:{relations['parent_job_id']}"
    elif relation_status == "not_applicable":
        answers["Q8"] = "none"
    else:
        answers["Q8"] = UNDETERMINABLE

    answers["Q9"] = (job.get("failure") or {}).get("code") or UNDETERMINABLE
    simulation = (record.get("extensions") or {}).get("simulation.ionq") or {}
    answers["Q10"] = simulation.get("noise_model") or UNDETERMINABLE
    answers["Q11"] = results.get("measurement_counts") or UNDETERMINABLE
    device = record.get("device") or {}
    identifier = device.get("identifier")
    answers["N1"] = identifier if identifier and identifier != "unknown" else UNDETERMINABLE
    answers["N2"] = _times(job.get("created_at"), job.get("ended_at"))
    answers["N3"] = device.get("qubit_count") or UNDETERMINABLE
    return answers


def _program_producer(record: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> str:
    """Producer of the most-processed program artifact the record carries."""

    artifacts = record.get("artifacts") or []
    for role in ("compiled", "executed", "submitted"):
        for index, artifact in enumerate(artifacts):
            if artifact.get("role") != role:
                continue
            if artifact.get("producer"):
                return "application" if artifact["producer"] == "application" else "provider"
            status = (evidence.get(f"/artifacts/{index}") or {}).get("status")
            if status in _PROVIDER_STATES:
                return "provider"
            if status == "application_captured":
                return "application"
    return UNDETERMINABLE


def score(answer: Any, truth: Any, question: str) -> str:
    if answer == "no_record":
        return "no_record"
    if question == "N2":
        return _score_times(answer, truth)
    if answer == UNDETERMINABLE or answer is None:
        return "undeterminable"
    if question == "N1":
        a, t = str(answer).lower(), str(truth).lower()
        return "correct" if a == t or t.endswith("/" + a) or a.endswith("/" + t) else "misleading"
    if isinstance(truth, str) and isinstance(answer, str):
        return "correct" if answer.lower() == truth.lower() else "misleading"
    return "correct" if answer == truth else "misleading"


def _score_times(answer: list[str | None], truth: list[str | None]) -> str:
    outcome = "correct"
    for given, expected in zip(answer, truth, strict=True):
        if expected is None:
            continue
        if given is None:
            outcome = "undeterminable"
            continue
        delta = abs((parse_time(given) - parse_time(expected)).total_seconds())
        if delta > 2:
            return "misleading"
    return outcome
