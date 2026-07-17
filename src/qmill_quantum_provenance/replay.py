"""Fixture replay for the integration ProviderAdapter seam.

The provenance adapters retrieve provider-native data through the existing
integration :class:`ProviderAdapter`. ``ReplayIntegrationAdapter`` implements
that seam from a captured, sanitized fixture so the representative
completed-job flow runs deterministically without network or credentials.
Real provider retrieval uses the concrete integration adapters instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .integration import ProviderAdapter
from .integration import ResultUnavailableError
from .integration import (
    DeviceDetails,
    ResolvedTarget,
    SubmissionResult,
    TargetInfo,
    TaskHandle,
    TaskResult,
    TaskSnapshot,
)


_COMPLETED_STATES = {"COMPLETED", "DONE"}


def _parse(value: Any) -> datetime | None:
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


class ReplayIntegrationAdapter(ProviderAdapter):
    """Replay a single captured job fixture through the integration contract."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self._fixture = fixture
        self._provider = str(fixture.get("provider", "braket"))

    # -- retrieval used by provenance adapters -------------------------------

    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        snapshot = self._fixture.get("snapshot", {})
        return TaskHandle(
            provider=self._provider,
            provider_job_id=provider_job_id,
            region=region or self._fixture.get("region"),
            target_id=snapshot.get("target_id"),
            provider_target_id=snapshot.get("provider_target_id"),
        )

    def get_status(self, task: TaskHandle) -> TaskSnapshot:
        snapshot = self._fixture.get("snapshot", {})
        return TaskSnapshot(
            provider=self._provider,
            provider_job_id=task.provider_job_id,
            status=str(snapshot.get("status", "UNKNOWN")),
            created_at=_parse(snapshot.get("created_at")),
            ended_at=_parse(snapshot.get("ended_at")),
            shots=snapshot.get("shots"),
            target_id=snapshot.get("target_id"),
            provider_target_id=snapshot.get("provider_target_id"),
            metadata=dict(snapshot.get("metadata", {})),
        )

    def get_result(self, task: TaskHandle) -> TaskResult:
        snapshot = self._fixture.get("snapshot", {})
        status = str(snapshot.get("status", "UNKNOWN"))
        result = self._fixture.get("result")
        if result is None or status.upper() not in _COMPLETED_STATES:
            raise ResultUnavailableError(f"Task is not complete: {status}")
        return TaskResult(
            provider=self._provider,
            provider_job_id=task.provider_job_id,
            status=status,
            measurement_counts=dict(result.get("measurement_counts", {})),
            compiled_circuit=result.get("compiled_circuit"),
            compiled_circuit_metrics=result.get("compiled_circuit_metrics"),
            raw_payload=result.get("raw_payload"),
        )

    def get_device_details(self, target_id: str, region: str | None = None) -> DeviceDetails:
        device = self._fixture.get("device")
        if device is None:
            raise ValueError(f"No device fixture for target {target_id}")
        return DeviceDetails(
            provider=self._provider,
            target_id=device.get("target_id", target_id),
            provider_target_id=device.get("provider_target_id", target_id),
            name=device.get("name"),
            type=device.get("type"),
            status=device.get("status"),
            calibration_data=device.get("calibration"),
            provider_properties=device.get("provider_properties"),
            metadata=device.get("metadata"),
        )

    def get_compiled_circuit(self, task: TaskHandle) -> str | None:
        result = self._fixture.get("result") or {}
        return result.get("compiled_circuit")

    # -- submission path is not exercised by provenance retrieval ------------

    def list_targets(self, region: str | None = None) -> list[TargetInfo]:
        raise NotImplementedError("ReplayIntegrationAdapter does not submit jobs")

    def resolve_target(self, target_id: str, region: str | None = None) -> ResolvedTarget:
        raise NotImplementedError("ReplayIntegrationAdapter does not submit jobs")

    def submit_openqasm(
        self,
        openqasm: str,
        shots: int,
        target: ResolvedTarget,
        s3_bucket: str | None = None,
        s3_prefix: str | None = None,
    ) -> SubmissionResult:
        raise NotImplementedError("ReplayIntegrationAdapter does not submit jobs")


__all__ = ["ReplayIntegrationAdapter"]
