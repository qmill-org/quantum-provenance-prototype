"""AWS Braket provenance adapter.

Reuses the existing integration :class:`ProviderAdapter` (submission/status/
result oriented) as the retrieval seam and maps Braket-native task data into
provider-independent record sections plus per-field evidence. The submission
path and executors are untouched.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from ..integration import ProviderAdapter, ResultUnavailableError
from ..adapter import (
    AdapterCapabilities,
    AdapterResult,
    ProvenanceAdapter,
    ProvenanceCollectionRequest,
)
from ..models import (
    Artifact,
    ArtifactRole,
    AvailabilityReason,
    Characterization,
    CharacterizationAssociation,
    CharacterizationMetric,
    ContentHash,
    Device,
    Evidence,
    EvidenceStatus,
    Execution,
    Job,
    OperationObservation,
    Results,
    Warning,
    canonical_job_id,  # noqa: F401  (re-exported convenience)
    normalize_device_type,
    normalize_job_status,
)
from ..redaction import redact

_QUBIT_COUNT_KEYS = ("qubitCount", "qubit_count", "num_qubits", "qubitcount")


def _sha256(text: str) -> ContentHash:
    return ContentHash("sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())


def _find_int(payload: Any, keys: tuple[str, ...], _depth: int = 0) -> int | None:
    if _depth > 8 or payload is None:
        return None
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and isinstance(value, int) and not isinstance(value, bool):
                return value
        for value in payload.values():
            found = _find_int(value, keys, _depth + 1)
            if found is not None:
                return found
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found = _find_int(item, keys, _depth + 1)
            if found is not None:
                return found
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _record_timestamp_evidence(snapshot, evidence: list[Evidence], provider_field: str) -> None:
    """Emit evidence for the job timestamps so they carry a provenance qualifier."""

    for path, value in (
        ("/job/created_at", snapshot.created_at),
        ("/job/ended_at", snapshot.ended_at),
    ):
        if value is not None:
            evidence.append(
                Evidence(
                    path=path,
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field=provider_field,
                )
            )
        else:
            evidence.append(
                Evidence(
                    path=path,
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                )
            )


def _hardware_provider_from_arn(identifier: str | None) -> str | None:
    """Extract the hardware operator from a Braket device ARN.

    ``arn:aws:braket:<region>::device/<category>/<vendor>/<name>`` -- the vendor
    segment following ``qpu`` or a ``*simulator*`` category names the operator of
    the physical (or simulated) device, e.g. ``ionq`` for an IonQ QPU accessed
    through Amazon Braket.
    """

    if not identifier or "/" not in identifier:
        return None
    parts = identifier.split("/")
    for index, part in enumerate(parts):
        if (part == "qpu" or "simulator" in part) and index + 1 < len(parts):
            return parts[index + 1].strip().lower() or None
    return None


class BraketProvenanceAdapter(ProvenanceAdapter):
    provider = "braket"
    name = "braket-provenance-adapter"
    version = "0.1.0-prototype"

    def __init__(self, integration_adapter: ProviderAdapter | None = None) -> None:
        self._integration = integration_adapter

    def _adapter(self) -> ProviderAdapter:
        if self._integration is not None:
            return self._integration
        raise NotImplementedError(
            "Live provider retrieval is not available in the artifact; supply a "
            "ReplayIntegrationAdapter (or another ProviderAdapter) explicitly."
        )

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            provider="braket",
            supports_result_counts=True,
            supports_compilation=True,
            supports_characterization=True,
            supports_execution_timing=True,
            notes="Compiled circuit is passthrough; execution timing is derived "
            "from created/ended timestamps.",
        )

    def collect(self, request: ProvenanceCollectionRequest) -> AdapterResult:
        integration = self._adapter()
        operations: list[OperationObservation] = []
        warnings: list[Warning] = []
        evidence: list[Evidence] = []
        artifacts: list[Artifact] = []

        handle = integration.get_task(request.external_job_id, region=request.region)
        operations.append(OperationObservation("adapter", "get_task"))

        snapshot = integration.get_status(handle)
        operations.append(OperationObservation("adapter", "get_status"))

        target = snapshot.provider_target_id or snapshot.target_id
        device_details = None
        if target:
            try:
                device_details = integration.get_device_details(target, region=request.region)
                operations.append(OperationObservation("adapter", "get_device_details"))
            except Exception as exc:  # provider/lookup failure is non-fatal
                warnings.append(Warning("device_details_unavailable", str(exc)))

        result_data = None
        try:
            result_data = integration.get_result(handle)
            operations.append(OperationObservation("adapter", "get_result"))
        except ResultUnavailableError as exc:
            warnings.append(Warning("results_unavailable", str(exc)))

        job = self._build_job(request, snapshot, evidence)
        device = self._build_device(target, device_details, evidence)
        results = self._build_results(snapshot, result_data, evidence)
        self._build_compiled_artifact(result_data, artifacts, evidence)
        self._build_provider_native_artifact(snapshot, artifacts, evidence)
        execution = self._build_execution(snapshot, evidence)
        characterization = self._build_characterization(device_details, evidence)

        return AdapterResult(
            job=job,
            device=device,
            results=results,
            artifacts=artifacts,
            evidence=evidence,
            warnings=warnings,
            operations=operations,
            execution=execution,
            characterization=characterization,
            retrieved_at=datetime.now(UTC),
        )

    # -- section builders ----------------------------------------------------

    def _build_job(self, request, snapshot, evidence: list[Evidence]) -> Job:
        status = normalize_job_status(snapshot.status)
        evidence.append(
            Evidence(
                path="/job/status",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field="AwsQuantumTask.state()",
            )
        )
        if snapshot.shots is not None:
            evidence.append(
                Evidence(
                    path="/job/shots",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="metadata.shots",
                )
            )
        _record_timestamp_evidence(
            snapshot, evidence, "AwsQuantumTask.metadata() createdAt/endedAt"
        )
        return Job(
            canonical_id=request.canonical_id,
            provider="braket",
            external_id=request.external_job_id,
            status=status,
            created_at=snapshot.created_at,
            ended_at=snapshot.ended_at,
            shots=snapshot.shots,
        )

    def _build_device(self, target, device_details, evidence: list[Evidence]) -> Device:
        identifier = target or "unknown"
        evidence.append(
            Evidence(
                path="/device/identifier",
                status=(EvidenceStatus.PROVIDER_SUPPLIED if target else EvidenceStatus.UNAVAILABLE),
                reason=None if target else AvailabilityReason.INSUFFICIENT_SOURCE_DATA,
                provider_field="metadata.deviceArn" if target else None,
            )
        )

        device_type = "unknown"
        name = None
        qubit_count = None
        if device_details is not None:
            device_type = normalize_device_type(device_details.type)
            name = device_details.name
            qubit_count = _find_int(
                device_details.provider_properties or device_details.metadata,
                _QUBIT_COUNT_KEYS,
            )

        if device_type != "unknown":
            evidence.append(
                Evidence(
                    path="/device/type",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="device_details.device_type",
                )
            )
        else:
            evidence.append(
                Evidence(
                    path="/device/type",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                )
            )

        if qubit_count is None:
            evidence.append(
                Evidence(
                    path="/device/qubit_count",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                )
            )
        else:
            evidence.append(
                Evidence(
                    path="/device/qubit_count",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="device_properties.qubitCount",
                )
            )

        hardware_provider = _hardware_provider_from_arn(target)
        evidence.append(
            Evidence(
                path="/device/platform_provider",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field="metadata.deviceArn (arn:aws:braket namespace)",
                notes="Job was submitted through the Amazon Braket aggregation platform.",
            )
        )
        if hardware_provider is not None:
            evidence.append(
                Evidence(
                    path="/device/hardware_provider",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/device/identifier"],
                    derivation="vendor segment of the Braket device ARN",
                    notes="Underlying hardware operator behind the Braket platform.",
                )
            )
        else:
            evidence.append(
                Evidence(
                    path="/device/hardware_provider",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.INSUFFICIENT_SOURCE_DATA,
                    notes="Device ARN did not identify a hardware vendor.",
                )
            )

        return Device(
            provider="braket",
            identifier=identifier,
            name=name,
            type=device_type,
            qubit_count=qubit_count,
            platform_provider="amazon_braket",
            hardware_provider=hardware_provider,
        )

    def _build_results(self, snapshot, result_data, evidence: list[Evidence]) -> Results:
        if result_data is not None and result_data.measurement_counts:
            evidence.append(
                Evidence(
                    path="/results/measurement_counts",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="GateModelQuantumTaskResult.measurement_counts",
                )
            )
            return Results(
                available=True,
                shots=snapshot.shots,
                measurement_counts=dict(result_data.measurement_counts),
            )

        evidence.append(
            Evidence(
                path="/results",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.UPSTREAM_REQUEST_FAILED,
            )
        )
        return Results(available=False, shots=snapshot.shots)

    def _build_compiled_artifact(
        self, result_data, artifacts: list[Artifact], evidence: list[Evidence]
    ) -> None:
        compiled = result_data.compiled_circuit if result_data is not None else None
        if compiled:
            index = len(artifacts)
            artifacts.append(
                Artifact(
                    role=ArtifactRole.COMPILED,
                    media_type="application/x-openqasm;version=3",
                    description="Provider-compiled program (passthrough, hash only).",
                    content_hash=_sha256(compiled),
                    byte_size=len(compiled.encode("utf-8")),
                )
            )
            evidence.append(
                Evidence(
                    path=f"/artifacts/{index}",
                    status=EvidenceStatus.PROVIDER_PASSTHROUGH,
                    provider_field="additionalMetadata.*.compiledProgram",
                )
            )
        else:
            evidence.append(
                Evidence(
                    path="/compilation",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                    notes="Simulator/QPU did not expose a compiled program.",
                )
            )

    def _build_provider_native_artifact(
        self, snapshot, artifacts: list[Artifact], evidence: list[Evidence]
    ) -> None:
        metadata = getattr(snapshot, "metadata", None)
        if not isinstance(metadata, dict) or not metadata:
            return
        sanitized = redact(metadata)
        canonical = json.dumps(sanitized, sort_keys=True, default=str)
        index = len(artifacts)
        artifacts.append(
            Artifact(
                role=ArtifactRole.PROVIDER_NATIVE,
                media_type="application/json",
                description="Sanitized Braket task metadata (content hash only).",
                content_hash=_sha256(canonical),
            )
        )
        evidence.append(
            Evidence(
                path=f"/artifacts/{index}",
                status=EvidenceStatus.PROVIDER_PASSTHROUGH,
                provider_field="AwsQuantumTask.metadata()",
                notes="Secrets redacted; only a content hash is retained.",
            )
        )

    def _build_execution(self, snapshot, evidence: list[Evidence]) -> Execution | None:
        created = snapshot.created_at
        ended = snapshot.ended_at
        if created is not None and ended is not None and ended >= created:
            total_ms = int((ended - created).total_seconds() * 1000)
            evidence.append(
                Evidence(
                    path="/execution/total_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/job/created_at", "/job/ended_at"],
                    derivation="ended_at - created_at",
                )
            )
            return Execution(total_duration_ms=total_ms)

        evidence.append(
            Evidence(
                path="/execution",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
            )
        )
        return None

    def _build_characterization(
        self, device_details, evidence: list[Evidence]
    ) -> Characterization | None:
        calibration = getattr(device_details, "calibration_data", None) if device_details else None
        if isinstance(calibration, dict) and calibration:
            metrics = self._extract_metrics(calibration)
            evidence.append(
                Evidence(
                    path="/characterization",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="device_details.calibration",
                    notes="Device calibration snapshot at retrieval time.",
                )
            )
            return Characterization(
                association=CharacterizationAssociation.CURRENT_AT_RETRIEVAL,
                captured_at=_parse_timestamp(calibration.get("captured_at")),
                metrics=metrics or None,
            )

        evidence.append(
            Evidence(
                path="/characterization",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes="No calibration snapshot available for this device/job.",
            )
        )
        return None

    @staticmethod
    def _extract_metrics(calibration: dict[str, Any]) -> list[CharacterizationMetric]:
        raw = calibration.get("metrics")
        metrics: list[CharacterizationMetric] = []
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    metrics.append(CharacterizationMetric(name=str(key), value=float(value)))
        return metrics


__all__ = ["BraketProvenanceAdapter"]
