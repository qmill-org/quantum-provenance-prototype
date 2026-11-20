"""Live Quandela Cloud retrieval through the integration ``ProviderAdapter`` seam.

Uses the Quandela client's own HTTP handler (Perceval ``RPCHandler``) for
``/api/job/status/{id}``, ``/api/job/result/{id}`` and
``/api/platforms/{name}``, and Perceval's deserializer for result payloads.

Choices that affect provenance semantics:

* Job references are ``<platform>/<job id>``. Neither the job status nor the
  job result names the platform, and the job listing endpoints are not
  available to a project token, so the platform comes from the application;
  ``notes["platform_source"]`` records that.
* ``measurement_counts`` hold the provider's ``BSCount`` keyed by Fock states
  (``|1,0,1,0>``). Provider ``shots`` (photon-detection events) and the
  accepted samples are kept apart.
* ``compiled_circuit`` is the provider's ``computed_experiment`` (the
  experiment as compiled onto the chip), serialized by Perceval.
* Platform ``perfs`` carry no timestamp: ``captured_at`` stays empty.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
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

CLOUD_URL = "https://api.cloud.quandela.com"
_SCALAR_PERFS = {
    "HOM (%)": ("hom_visibility", "%"),
    "g2 (%)": ("g2", "%"),
    "Transmittance (%)": ("transmittance", "%"),
    "Clock (MHz)": ("clock", "MHz"),
}
_PLATFORM_FIELDS = (
    "constraints",
    "detector",
    "connected_input_modes",
    "known_mitigations",
    "available_commands",
    "pcvl_version",
    "software_versions",
)


def _epoch(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).isoformat()
    return None


def _translate(exc: Exception, what: str) -> ProviderIntegrationError:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    text = f"{what}: {type(exc).__name__}: {exc}"
    if status == 404:
        return JobNotFoundError(text)
    if status in (401, 403):
        return AccessDeniedError(text)
    if status == 429:
        return ThrottledError(text)
    return ProviderIntegrationError(text)


def split_reference(reference: str) -> tuple[str, str]:
    platform, sep, job_id = reference.rpartition("/")
    if not sep or not platform:
        raise ValueError(f"Quandela job reference must be '<platform>/<job id>': {reference!r}")
    return platform, job_id


def summarize_perfs(perfs: dict[str, Any]) -> dict[str, Any] | None:
    metrics = {
        f"{name}[{unit}]": float(perfs[key])
        for key, (name, unit) in _SCALAR_PERFS.items()
        if isinstance(perfs.get(key), (int, float))
    }
    if not metrics:
        return None
    return {
        "captured_at": None,
        "metrics": metrics,
        "per_mode_transmission": perfs.get("Transmission per mode (%)"),
        "dark_counts_per_detector": perfs.get("Dark counts (detection/s)"),
    }


class LiveQuandelaIntegration(ProviderAdapter):
    """Retrieval against Quandela Cloud with a project token."""

    provider = "quandela"

    def __init__(self, handler_factory: Any | None = None) -> None:
        if handler_factory is None:
            from perceval.providers.quandela.rpc_handler import RPCHandler

            token = os.environ["QUANDELA_TOKEN"]

            def handler_factory(platform: str):
                return RPCHandler(platform, CLOUD_URL, token)

        self._handler_factory = handler_factory
        self._status: dict[str, Any] | None = None
        self.native: dict[str, Any] = {}
        self.notes: dict[str, Any] = {"platform_source": "application_reference"}

    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        platform, job_id = split_reference(provider_job_id)
        return TaskHandle(
            provider="quandela",
            provider_job_id=provider_job_id,
            target_id=platform,
            provider_target_id=platform,
            raw_task=job_id,
        )

    def get_status(self, task: TaskHandle) -> TaskSnapshot:
        try:
            status = self._handler_factory(task.target_id).get_job_status(task.raw_task)
        except Exception as exc:
            raise _translate(exc, "GET /api/job/status") from exc
        self._status = status
        self.native["job_status"] = status
        return TaskSnapshot(
            provider="quandela",
            provider_job_id=task.provider_job_id,
            status=str(status.get("status", "unknown")),
            created_at=_epoch(status.get("creation_datetime")),
            ended_at=None,
            shots=status.get("shots"),
            target_id=task.target_id,
            provider_target_id=task.target_id,
            metadata={
                k: status.get(k)
                for k in (
                    "creation_datetime",
                    "start_time",
                    "duration",
                    "shots",
                    "failure_code",
                    "status_message",
                    "progress",
                )
            },
        )

    def get_result(self, task: TaskHandle) -> TaskResult:
        status = self._status or {}
        if str(status.get("status")) != "completed":
            raise ResultUnavailableError(
                f"Job is {status.get('status')}"
                + (f": {status.get('failure_code')}" if status.get("failure_code") else "")
            )
        try:
            response = self._handler_factory(task.target_id).get_job_results(task.raw_task)
        except Exception as exc:
            raise _translate(exc, "GET /api/job/result") from exc
        from perceval.serialization import deserialize

        try:
            inner = (
                json.loads(response["results"]) if isinstance(response.get("results"), str) else {}
            )
            counts_obj = deserialize(inner["results"]) if "results" in inner else {}
            counts = {str(state): int(n) for state, n in dict(counts_obj).items()}
            compiled = inner.get("computed_experiment")
            compiled_modes = getattr(deserialize(compiled), "m", None) if compiled else None
        except Exception as exc:  # malformed or truncated result document
            raise ProviderIntegrationError(f"job result document unreadable: {exc}") from exc
        self.native["job_result"] = {
            "job_id": response.get("job_id"),
            "shots": response.get("shots"),
            "duration": response.get("duration"),
            "results_type": response.get("results_type"),
            "intermediate_results": response.get("intermediate_results"),
            "counts": counts,
            **{k: inner[k] for k in ("physical_perf", "logical_perf", "global_perf") if k in inner},
            "computed_experiment_modes": compiled_modes,
        }
        self.notes["measurement_counts_origin"] = "observed_samples_fock_states"
        self.notes["compiled_program_origin"] = (
            "provider_compiled_artifact" if compiled else "absent"
        )
        return TaskResult(
            provider="quandela",
            provider_job_id=task.provider_job_id,
            status="completed",
            measurement_counts=counts,
            compiled_circuit=compiled,
            compiled_circuit_metrics={"modes": compiled_modes} if compiled_modes else None,
            raw_payload={
                k: v for k, v in self.native["job_result"].items() if k not in {"counts", "job_id"}
            },
        )

    def get_compiled_circuit(self, task: TaskHandle) -> str | None:
        return None

    def get_device_details(self, target_id: str, region: str | None = None) -> DeviceDetails:
        try:
            details = self._handler_factory(target_id).fetch_platform_details()
        except Exception as exc:
            raise _translate(exc, "GET /api/platforms") from exc
        specs = details.get("specs") or {}
        self.native["platform"] = {
            "name": target_id,
            "type": details.get("type"),
            "status": details.get("status"),
            "perfs": details.get("perfs"),
            "specs": {k: specs.get(k) for k in _PLATFORM_FIELDS if k in specs},
        }
        return DeviceDetails(
            provider="quandela",
            target_id=target_id,
            provider_target_id=target_id,
            name=specs.get("description") or target_id,
            type=details.get("type"),
            status=details.get("status"),
            calibration_data=summarize_perfs(details.get("perfs") or {}),
            provider_properties={k: specs.get(k) for k in _PLATFORM_FIELDS if k in specs},
            metadata={"provider": "Quandela"},
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


__all__ = ["LiveQuandelaIntegration", "split_reference", "summarize_perfs"]
