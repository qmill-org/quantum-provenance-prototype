"""Ground truth per capture, from raw provider responses (``native.json``),
the capture manifest and the application's run ledgers.

The oracle never calls an arm's mapping code. A question it cannot answer for a
capture is omitted (not applicable). Answers use the vocabulary of
:mod:`.readers`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_NOT_RUN = {"cancelled", "canceled", "failed", "error"}
_PENDING = {"created", "queued", "running", "waiting", "ready", "submitted", "initializing"}


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def load_ledgers(runs: Path) -> dict[str, dict[str, Any]]:
    """Application requests keyed by provider job id (ARN suffix for Braket)."""

    requests: dict[str, dict[str, Any]] = {}
    for path in sorted(runs.glob("ledger*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            job = entry.get("job_id") or str(entry.get("task_arn") or "").rsplit("/", 1)[-1]
            if job and entry.get("outcome", "created") == "created":
                requests[job] = entry
    return requests


_AHS_STATES = "erg"


def tally_shots(measurements: list[Any]) -> dict[str, int]:
    """Outcome counts from raw per-shot data (Q11, added after the freeze).

    Gate-model shots are bit lists. Analog (AHS) shots use the Braket SDK's
    documented convention: an empty site is ``e``, a Rydberg atom (post 0) ``r``,
    a ground-state atom ``g``; only successful shots count.
    """

    counts: dict[str, int] = {}
    for shot in measurements:
        if isinstance(shot, dict):
            if (shot.get("shotMetadata") or {}).get("shotStatus") != "Success":
                continue
            result = shot.get("shotResult") or {}
            pre, post = result.get("preSequence") or [], result.get("postSequence") or []
            key = "".join(
                _AHS_STATES[0 if a == 0 else 1 if b == 0 else 2]
                for a, b in zip(pre, post, strict=True)
            )
        else:
            key = "".join(str(bit) for bit in shot)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _relation(kind: str | None, ident: str | None) -> str:
    return f"{kind}:{ident}" if ident else "none"


def truth(directory: Path, ledgers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fixture = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    native = json.loads((directory / "native.json").read_text(encoding="utf-8"))
    provider = fixture["provider"]
    notes = manifest.get("notes") or {}
    upstream = {op["operation"]: op["outcome"] for op in manifest["operations"]}
    request = ledgers.get(directory.name, {})
    answers: dict[str, Any] = {"Q0": True}

    if upstream.get("get_status") == "JobNotFoundError":
        answers["Q5"] = "not_retrievable"
        return answers

    status, created, ended, device_id, qubits = None, None, None, None, None
    relation: str | None = None
    if provider == "braket":
        task = native.get("get_quantum_task") or {}
        status = str(task.get("status", "")).lower()
        created, ended = parse_time(task.get("createdAt")), parse_time(task.get("endedAt"))
        device_id = task.get("deviceArn")
        answers["Q4"] = str(device_id).split("/")[-2].lower()
        relation = _relation("parent", task.get("jobArn"))
        capabilities = (native.get("get_device") or {}).get("deviceCapabilities")
        if isinstance(capabilities, str):
            capabilities = json.loads(capabilities)
        qubits = ((capabilities or {}).get("paradigm") or {}).get("qubitCount")
        results = native.get("results_json") or {}
        if results.get("measurements"):
            answers["Q1"] = "observed_counts"
            answers["Q7"] = len(results["measurements"])
            answers["Q11"] = tally_shots(results["measurements"])
        elif results.get("measurementProbabilities"):
            answers["Q1"] = "probabilities"
        compiled = notes.get("compiled_program")
        if compiled == "present":
            answers["Q2"] = "provider"
        elif notes.get("submitted_program_available"):
            answers["Q2"] = "application"
    elif provider == "ibm":
        job = native.get("job") or {}
        status = str(job.get("status", "")).lower()
        stamps = (native.get("metrics") or {}).get("timestamps") or {}
        created, ended = parse_time(stamps.get("created")), parse_time(stamps.get("finished"))
        device_id = job.get("backend")
        answers["Q4"] = "ibm"
        qubits = (native.get("backend_configuration") or {}).get("n_qubits")
        session = native.get("session") or {}
        relation = _relation(
            "batch" if session.get("mode") == "batch" else "session", job.get("session_id")
        )
        origin = str(notes.get("measurement_counts_origin") or "")
        if origin.startswith("observed_samples"):
            answers["Q1"] = "observed_counts"
        elif origin.startswith("expectation_values"):
            answers["Q1"] = "client_derived"
        if notes.get("compiled_program_origin") == "application_compiled_job_input":
            answers["Q2"] = "application"
        executed = (fixture.get("snapshot") or {}).get("metadata", {}).get("executed_shots")
        if executed is not None:
            answers["Q7"] = executed
    elif provider == "ionq":
        job = native.get("job") or {}
        status = str(job.get("status", "")).lower()
        created, ended = parse_time(job.get("submitted_at")), parse_time(job.get("completed_at"))
        device_id = job.get("backend")
        answers["Q4"] = "ionq"
        qubits = (native.get("backend") or {}).get("qubits")
        relation = (
            _relation("session", job.get("session_id"))
            if job.get("session_id")
            else _relation("parent", job.get("parent_job_id"))
        )
        if native.get("probabilities"):
            answers["Q1"] = "probabilities"
        if notes.get("compiled_program_origin") == "provider_compiled_artifact":
            answers["Q2"] = "provider"
        noise = job.get("noise") or {}
        if device_id == "simulator" and noise.get("model"):
            answers["Q10"] = noise["model"]
            if noise["model"] == "ideal" and status == "completed":
                answers["Q7"] = "none"
        if (job.get("failure") or {}).get("code"):
            answers["Q9"] = job["failure"]["code"]
    elif provider == "quandela":
        job_status = native.get("job_status") or {}
        status = str(job_status.get("status", "")).lower()
        created = parse_time(job_status.get("creation_datetime"))
        start = parse_time(job_status.get("start_time"))
        if start and job_status.get("duration") is not None:
            ended = start + timedelta(seconds=job_status["duration"])
        device_id = request.get("platform")
        answers["Q4"] = "quandela"
        if native.get("job_result"):
            answers["Q1"] = "observed_counts"
            if isinstance(native["job_result"].get("counts"), dict):
                answers["Q11"] = native["job_result"]["counts"]
        if notes.get("compiled_program_origin") == "provider_compiled_artifact":
            answers["Q2"] = "provider"
        if status == "completed" and job_status.get("shots") is not None:
            answers["Q7"] = job_status["shots"]
    if relation is not None and provider != "quandela":
        answers["Q8"] = relation

    if status in _NOT_RUN:
        answers["Q5"] = "did_not_run"
        for key in ("Q1", "Q7"):
            answers.pop(key, None)
    elif status in _PENDING:
        answers["Q5"] = "not_yet"

    calibration = (fixture.get("device") or {}).get("calibration") or {}
    if status in _NOT_RUN and calibration:
        answers["Q3"] = "no_execution"
    elif calibration:
        answers["Q3"] = time_relation(parse_time(calibration.get("captured_at")), created, ended)

    shots = request.get("max_samples") if provider == "quandela" else request.get("shots")
    if shots is not None:
        answers["Q6"] = shots
    if device_id:
        answers["N1"] = device_id
    if created or ended:
        answers["N2"] = [
            created.isoformat() if created else None,
            ended.isoformat() if ended else None,
        ]
    if qubits is not None:
        answers["N3"] = qubits
    return answers


def time_relation(
    captured: datetime | None, created: datetime | None, ended: datetime | None
) -> str:
    """How a characterization snapshot relates in time to the execution."""

    if captured is None:
        return "unknown_time"
    if ended is not None and captured > ended:
        return "after_end"
    return "matched"
