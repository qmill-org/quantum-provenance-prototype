"""Live IonQ retrieval through the integration ``ProviderAdapter`` seam (API v0.4).

Maps ``GET /jobs/{id}``, ``GET /jobs/{id}/results/probabilities``, the job's
compiled-circuit artifact, ``GET /backends/{backend}`` and the backend's
characterization history into the integration data transfer objects.

Choices that affect provenance semantics:

* Provider job fields are passed through under their v0.4 names (for example
  ``execution_duration_ms``); nothing is renamed to fit an adapter.
* IonQ returns probabilities, not counts: ``measurement_counts`` stays empty
  and the probabilities go to ``raw_payload["histogram"]``.
* For QPU backends the characterization is the latest one dated at or before
  job submission (``GET /backends/{b}/characterizations?end=…``); v0.4 jobs
  carry no characterization identifier, so the link is by timestamp.
* ``compiled_circuit`` is the provider-compiled ``ionq.qasm3.v1`` artifact.
"""

from __future__ import annotations

import os
from typing import Any

from ..integration import (
    AccessDeniedError,
    DeviceDetails,
    JobNotFoundError,
    ProviderAdapter,
    ProviderIntegrationError,
    ResolvedTarget,
    ResultUnavailableError,
    SubmissionResult,
    TargetInfo,
    TaskHandle,
    TaskResult,
    TaskSnapshot,
    ThrottledError,
)

API = "https://api.ionq.co/v0.4"
_PASSTHROUGH_FIELDS = (
    "name",
    "type",
    "execution_duration_ms",
    "predicted_execution_duration_ms",
    "predicted_wait_time_ms",
    "session_id",
    "parent_job_id",
    "child_job_ids",
    "noise",
    "settings",
    "stats",
    "failure",
    "dry_run",
)


def summarize_characterization(char: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, float] = {}
    for group in ("fidelity", "timing"):
        for key, value in (char.get(group) or {}).items():
            if isinstance(value, dict) and isinstance(value.get("median"), (int, float)):
                metrics[f"{group}.{key}.median"] = float(value["median"])
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[f"{group}.{key}" + ("[s]" if group == "timing" else "")] = float(value)
    return {
        "captured_at": char.get("date"),
        "characterization_id": char.get("id"),
        "metrics": metrics,
    }


class LiveIonQIntegration(ProviderAdapter):
    """Retrieval against the IonQ Quantum Cloud REST API v0.4."""

    provider = "ionq"

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import httpx

            client = httpx.Client(
                base_url=API,
                headers={"Authorization": f"apiKey {os.environ['IONQ_API_KEY']}"},
                timeout=60,
            )
        self._client = client
        self._jobs: dict[str, dict[str, Any]] = {}
        self.native: dict[str, Any] = {}
        self.notes: dict[str, Any] = {}

    def _get(self, path: str, what: str, **params: Any):
        response = self._client.get(path, params=params or None)
        status = response.status_code
        if status == 404:
            raise JobNotFoundError(f"{what}: HTTP 404")
        if status in (401, 403):
            raise AccessDeniedError(f"{what}: HTTP {status}")
        if status == 429:
            raise ThrottledError(f"{what}: HTTP 429")
        if status >= 400:
            raise ProviderIntegrationError(f"{what}: HTTP {status}: {response.text[:200]}")
        return response

    def _job(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._jobs:
            self._jobs[job_id] = self._get(f"/jobs/{job_id}", "GetJob").json()
            self.native["job"] = self._jobs[job_id]
        return self._jobs[job_id]

    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        return TaskHandle(provider="ionq", provider_job_id=provider_job_id)

    def get_status(self, task: TaskHandle) -> TaskSnapshot:
        job = self._job(task.provider_job_id)
        backend = job.get("backend")
        task.target_id = task.provider_target_id = backend
        return TaskSnapshot(
            provider="ionq",
            provider_job_id=task.provider_job_id,
            status=str(job.get("status", "unknown")),
            created_at=job.get("submitted_at"),
            ended_at=job.get("completed_at"),
            shots=job.get("shots"),
            target_id=backend,
            provider_target_id=backend,
            metadata={k: job[k] for k in _PASSTHROUGH_FIELDS if k in job},
        )

    def get_result(self, task: TaskHandle) -> TaskResult:
        job = self._job(task.provider_job_id)
        status = str(job.get("status"))
        if status != "completed":
            failure = job.get("failure")
            raise ResultUnavailableError(f"Job is {status}" + (f": {failure}" if failure else ""))
        # Follow the location the job advertises (F16); multi-circuit jobs keep
        # their results elsewhere, keyed by child job.
        advertised = ((job.get("results") or {}).get("probabilities") or {}).get("url")
        path = (
            advertised.removeprefix("/v0.4")
            if advertised
            else f"/jobs/{task.provider_job_id}/results/probabilities"
        )
        probabilities = self._get(path, "GetJobProbabilities").json()
        multi = job.get("type") == "ionq.multi-circuit.v1"
        self.native["per_child_probabilities" if multi else "probabilities"] = probabilities
        self.notes["measurement_counts_origin"] = (
            "per_child_job_results" if multi else "none_provider_returns_probabilities"
        )
        payload = (
            {"per_child_probabilities": probabilities}
            if multi
            else {"histogram": probabilities, "qubits": (job.get("stats") or {}).get("qubits")}
        )
        return TaskResult(
            provider="ionq",
            provider_job_id=task.provider_job_id,
            status=status,
            measurement_counts={},
            compiled_circuit=self.get_compiled_circuit(task),
            compiled_circuit_metrics=(job.get("stats") or None),
            raw_payload=payload,
        )

    def get_compiled_circuit(self, task: TaskHandle) -> str | None:
        compiled = (
            (self._job(task.provider_job_id).get("output") or {}).get("compilation") or {}
        ).get("compiled_circuits") or {}
        descriptor = compiled.get("ionq.qasm3.v1")
        if not descriptor:
            self.notes["compiled_program_origin"] = "absent"
            return None
        text = self._get(
            f"/jobs/{task.provider_job_id}/artifacts/{descriptor['id']}", "GetJobArtifact"
        ).text
        self.notes["compiled_program_origin"] = "provider_compiled_artifact"
        return text

    def get_device_details(self, target_id: str, region: str | None = None) -> DeviceDetails:
        backend = self._get(f"/backends/{target_id}", "GetBackend").json()
        self.native["backend"] = backend
        calibration = None
        submitted = next(iter(self._jobs.values()), {}).get("submitted_at")
        if target_id.startswith("qpu.") and submitted:
            history = self._get(
                f"/backends/{target_id}/characterizations",
                "GetCharacterizations",
                end=submitted,
                limit=1,
            ).json()
            items = history.get("characterizations") or []
            if items:
                self.native["characterization"] = items[0]
                calibration = summarize_characterization(items[0])
                calibration["query"] = "latest_at_or_before_submission"
            self.notes["characterization_query"] = "latest_at_or_before_submission"
        return DeviceDetails(
            provider="ionq",
            target_id=target_id,
            provider_target_id=target_id,
            name=backend.get("backend", target_id),
            type="SIMULATOR" if target_id == "simulator" else "QPU",
            status=backend.get("status"),
            calibration_data=calibration,
            provider_properties={"qubits": backend.get("qubits")},
            metadata={
                "provider": "IonQ",
                "current_characterization_id": backend.get("characterization_id"),
            },
        )

    # -- submission is out of scope for provenance retrieval -----------------

    def list_targets(self, region: str | None = None) -> list[TargetInfo]:
        raise NotImplementedError

    def resolve_target(self, target_id: str, region: str | None = None) -> ResolvedTarget:
        raise NotImplementedError

    def submit_openqasm(
        self,
        openqasm: str,
        shots: int,
        target: ResolvedTarget,
        s3_bucket: str | None = None,
        s3_prefix: str | None = None,
    ) -> SubmissionResult:
        raise NotImplementedError


__all__ = ["LiveIonQIntegration", "summarize_characterization"]
