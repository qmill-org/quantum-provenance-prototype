"""Arm B: a flat, QProv-aligned record without evidence qualification.

Each field is filled from the integration seam with the most direct accessor,
as a developer using the provider SDK's default accessors would. Nothing is
qualified: no evidence, association, missingness or producer. If retrieving
the job fails, no record is produced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..integration import ProviderIntegrationError
from ..replay import ReplayIntegrationAdapter


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


_QUBIT_KEYS = ("qubitCount", "qubit_count", "num_qubits", "n_qubits", "qubits")


def _find_count(value: Any, depth: int = 0) -> int | None:
    """First integer under a qubit-count key, searching nested properties."""

    if depth > 6:
        return None
    if isinstance(value, dict):
        for key in _QUBIT_KEYS:
            if isinstance(value.get(key), int) and not isinstance(value.get(key), bool):
                return value[key]
        for child in value.values():
            found = _find_count(child, depth + 1)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_count(child, depth + 1)
            if found is not None:
                return found
    return None


def flat_record(fixture: dict[str, Any]) -> dict[str, Any] | None:
    integration = ReplayIntegrationAdapter(fixture)
    try:
        handle = integration.get_task(str(fixture["external_job_id"]), fixture.get("region"))
        snapshot = integration.get_status(handle)
    except ProviderIntegrationError:
        return None
    device = None
    try:
        device = integration.get_device_details(
            snapshot.target_id or handle.target_id or "", fixture.get("region")
        )
    except (ProviderIntegrationError, ValueError):
        pass
    result = None
    try:
        result = integration.get_result(handle)
    except ProviderIntegrationError:
        pass
    calibration = (device.calibration_data or None) if device else None
    created, ended = snapshot.created_at, snapshot.ended_at
    run_ms = None
    if isinstance(created, datetime) and isinstance(ended, datetime):
        run_ms = int((ended - created).total_seconds() * 1000)
    properties = (device.provider_properties or {}) if device else {}
    return {
        "provider": fixture["provider"],
        "job_id": fixture["external_job_id"],
        "status": str(snapshot.status).lower() if snapshot.status else None,
        "created_at": _iso(created),
        "ended_at": _iso(ended),
        "shots": snapshot.shots,
        "qpu_name": snapshot.target_id or (device.name if device else None),
        "is_simulator": (str(device.type).lower() == "simulator") if device else None,
        "qubit_count": _find_count(properties),
        "last_calibrated": (calibration or {}).get("captured_at"),
        "calibration": (calibration or {}).get("metrics"),
        "counts": (result.measurement_counts or None) if result else None,
        "compiled_circuit": (result.compiled_circuit or None) if result else None,
        "execution_time_ms": run_ms,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
