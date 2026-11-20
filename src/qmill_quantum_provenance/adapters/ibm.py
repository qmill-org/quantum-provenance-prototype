"""IBM Quantum (Qiskit Runtime) provenance adapter.

Reuses the existing integration :class:`ProviderAdapter` (submission/status/
result oriented) as the retrieval seam and maps IBM Runtime job data into
provider-independent record sections plus per-field evidence. The submission
path and executors are untouched.

IBM-specific handling that distinguishes this adapter from Braket:

* Execution timing is split into queue/run/total using the Runtime
  ``metrics().timestamps`` (``created``/``running``/``finished``), with a
  graceful fallback to a single total duration when the finer timestamps are
  absent.
* Characterization metrics come from ``IBMBackend.properties()`` and are
  associated as ``nearest_available``: the calibration snapshot returned at
  retrieval time, which the provider does not guarantee was the one in force
  during execution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from ..integration import ProviderAdapter, ProviderIntegrationError
from ..adapter import (
    failure_with_evidence,
    relations_with_evidence,
    characterization_applies,
    delta_seconds,
    RESULT_REPRESENTATIONS,
    mark_not_applicable,
    qualify_missing_results,
    AdapterCapabilities,
    AdapterResult,
    ProvenanceAdapter,
    ProvenanceCollectionRequest,
)
from ..models import (
    JobRelations,
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
    normalize_device_type,
    normalize_job_status,
)
from ..redaction import program_digest, redact

_QUBIT_COUNT_KEYS = ("num_qubits", "n_qubits", "qubitCount", "qubit_count")


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


def _metric_unit(name: str) -> str | None:
    lowered = name.lower()
    if lowered.endswith("_us") or "_t1" in lowered or "_t2" in lowered:
        return "microseconds"
    if "error" in lowered or "fidelity" in lowered or "prob" in lowered:
        return None
    return None


class IBMProvenanceAdapter(ProvenanceAdapter):
    provider = "ibm"
    name = "ibm-provenance-adapter"
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
            provider="ibm",
            supports_result_counts=True,
            supports_compilation=True,
            supports_characterization=True,
            supports_execution_timing=True,
            notes="Execution timing is split into queue/run/total from Runtime "
            "metrics timestamps; characterization is the nearest-available "
            "backend properties snapshot, with the temporal delta reported and "
            "no claim that the snapshot was in force during execution.",
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
        result_error: ProviderIntegrationError | None = None
        try:
            result_data = integration.get_result(handle)
            operations.append(OperationObservation("adapter", "get_result"))
        except ProviderIntegrationError as exc:
            result_error = exc
            warnings.append(Warning("results_unavailable", str(exc)))

        job = self._build_job(request, snapshot, evidence)
        device = self._build_device(target, device_details, evidence)
        results = self._build_results(snapshot, result_data, evidence)
        if not results.available:
            qualify_missing_results(evidence, job.status, result_error)
        self._build_compiled_artifact(result_data, artifacts, evidence)
        self._build_provider_native_artifact(snapshot, artifacts, evidence)
        execution = self._build_execution(snapshot, evidence)
        characterization = self._build_characterization(device_details, job, evidence)

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
                provider_field="RuntimeJobV2.status()",
            )
        )
        if snapshot.shots is not None:
            evidence.append(
                Evidence(
                    path="/job/shots",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="RuntimeJobV2.metrics().usage / metadata.shots",
                )
            )
        _record_timestamp_evidence(snapshot, evidence, "RuntimeJobV2.metrics() timestamps")
        metadata = snapshot.metadata or {}
        session_id = metadata.get("session_id")
        mode = metadata.get("session_mode")
        relations = relations_with_evidence(
            evidence,
            exposed="session_id" in metadata,
            provider_field="RuntimeJobV2.session_id; sessions/{id}.mode",
            relations=JobRelations(
                batch_id=session_id if mode == "batch" else None,
                session_id=session_id if mode != "batch" else None,
            ),
            notes=(
                f"execution mode {mode!r}"
                if session_id and mode
                else "session mode not retrieved; grouping kind unknown"
                if session_id
                else None
            ),
        )
        failure = failure_with_evidence(
            evidence,
            status,
            provider_field="RuntimeJobV2.error_message()",
            message=metadata.get("error_message"),
        )
        return Job(
            canonical_id=request.canonical_id,
            provider="ibm",
            external_id=request.external_job_id,
            status=status,
            created_at=snapshot.created_at,
            ended_at=snapshot.ended_at,
            shots=snapshot.shots,
            relations=relations,
            failure=failure,
        )

    def _build_device(self, target, device_details, evidence: list[Evidence]) -> Device:
        identifier = target or "unknown"
        evidence.append(
            Evidence(
                path="/device/identifier",
                status=(EvidenceStatus.PROVIDER_SUPPLIED if target else EvidenceStatus.UNAVAILABLE),
                reason=None if target else AvailabilityReason.INSUFFICIENT_SOURCE_DATA,
                provider_field="RuntimeJobV2.backend().name" if target else None,
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
                    provider_field="IBMBackend.simulator / processor_type",
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
                    provider_field="IBMBackend.num_qubits",
                )
            )

        evidence.append(
            Evidence(
                path="/device/platform_provider",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field="RuntimeJobV2 (IBM Quantum Platform)",
                notes="Job was submitted through IBM Quantum, a direct provider platform.",
            )
        )
        evidence.append(
            Evidence(
                path="/device/hardware_provider",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field="RuntimeJobV2.backend()",
                notes="IBM operates the physical device directly.",
            )
        )

        return Device(
            provider="ibm",
            identifier=identifier,
            name=name,
            type=device_type,
            qubit_count=qubit_count,
            platform_provider="ibm_quantum",
            hardware_provider="ibm",
        )

    def _build_results(self, snapshot, result_data, evidence: list[Evidence]) -> Results:
        if result_data is not None and result_data.measurement_counts:
            evidence.append(
                Evidence(
                    path="/results/measurement_counts",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="PrimitiveResult[0].data.<register>.get_counts()",
                )
            )
            mark_not_applicable(
                evidence,
                RESULT_REPRESENTATIONS[1:],
                "Observed per-shot counts; no probability representation.",
            )
            return Results(
                available=True,
                shots=snapshot.shots,
                outcome_basis="bitstring",
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
            digest, size = program_digest(compiled)
            index = len(artifacts)
            artifacts.append(
                Artifact(
                    role=ArtifactRole.SUBMITTED,
                    media_type="application/x-openqasm;version=3",
                    producer="application",
                    description="ISA circuit compiled and submitted by the application, "
                    "returned by IBM with the job inputs (hash only).",
                    content_hash=ContentHash("sha256", digest),
                    byte_size=size,
                )
            )
            evidence.append(
                Evidence(
                    path=f"/artifacts/{index}",
                    status=EvidenceStatus.PROVIDER_PASSTHROUGH,
                    provider_field="RuntimeJobV2.inputs ISA circuit",
                    notes="Sampler/Estimator V2 run application-compiled ISA circuits; "
                    "IBM returns no provider-compiled program.",
                )
            )
            evidence.append(
                Evidence(
                    path="/compilation",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                    notes="No provider-compiled program; compilation happened in the application.",
                )
            )
        else:
            evidence.append(
                Evidence(
                    path="/compilation",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                    notes="No ISA circuit was returned with the job result.",
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
                description="Sanitized IBM Runtime job metadata (content hash only).",
                content_hash=_sha256(canonical),
            )
        )
        evidence.append(
            Evidence(
                path=f"/artifacts/{index}",
                status=EvidenceStatus.PROVIDER_PASSTHROUGH,
                provider_field="RuntimeJobV2.metrics()",
                notes="Secrets redacted; only a content hash is retained.",
            )
        )

    def _build_execution(self, snapshot, evidence: list[Evidence]) -> Execution | None:
        timestamps = {}
        metadata = getattr(snapshot, "metadata", None)
        if isinstance(metadata, dict):
            raw = metadata.get("timestamps")
            if isinstance(raw, dict):
                timestamps = raw

        created = _parse_timestamp(timestamps.get("created")) or snapshot.created_at
        running = _parse_timestamp(timestamps.get("running"))
        finished = _parse_timestamp(timestamps.get("finished")) or snapshot.ended_at

        # Preferred IBM path: queue/run split from Runtime metrics timestamps.
        if (
            created is not None
            and running is not None
            and finished is not None
            and running >= created
            and finished >= running
        ):
            evidence.append(
                Evidence(
                    path="/execution/queue_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/job/created_at", "/execution/_timestamps/running"],
                    derivation="running - created",
                    provider_field="RuntimeJobV2.metrics().timestamps",
                )
            )
            evidence.append(
                Evidence(
                    path="/execution/run_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/execution/_timestamps/running", "/job/ended_at"],
                    derivation="finished - running",
                    provider_field="RuntimeJobV2.metrics().timestamps",
                )
            )
            evidence.append(
                Evidence(
                    path="/execution/total_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/job/created_at", "/job/ended_at"],
                    derivation="finished - created",
                )
            )
            return Execution(
                queue_duration_ms=int((running - created).total_seconds() * 1000),
                run_duration_ms=int((finished - running).total_seconds() * 1000),
                total_duration_ms=int((finished - created).total_seconds() * 1000),
            )

        # Fallback: only a single total duration is derivable.
        if created is not None and finished is not None and finished >= created:
            evidence.append(
                Evidence(
                    path="/execution/total_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/job/created_at", "/job/ended_at"],
                    derivation="finished - created",
                    notes="Queue/run split unavailable; only total duration derived.",
                )
            )
            return Execution(total_duration_ms=int((finished - created).total_seconds() * 1000))

        evidence.append(
            Evidence(
                path="/execution",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
            )
        )
        return None

    def _build_characterization(
        self, device_details, job, evidence: list[Evidence]
    ) -> Characterization | None:
        if not characterization_applies(job.status, evidence):
            return None
        calibration = getattr(device_details, "calibration_data", None) if device_details else None
        if isinstance(calibration, dict) and calibration:
            metrics = self._extract_metrics(calibration)
            captured_at = _parse_timestamp(
                calibration.get("captured_at") or calibration.get("last_update_date")
            )
            matched = calibration.get("query") == "as_of_job_creation"
            delta = delta_seconds(captured_at, job.created_at)
            if matched:
                association = CharacterizationAssociation.TIMESTAMP_MATCHED
                note = (
                    "Backend properties requested as of job creation; IBM returns the "
                    "latest snapshot at or before that time."
                )
            else:
                association = CharacterizationAssociation.NEAREST_AVAILABLE
                note = (
                    "Nearest available backend properties snapshot; no provider guarantee "
                    "that it was in force during execution."
                )
            evidence.append(
                Evidence(
                    path="/characterization",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="IBMBackend.properties()",
                    notes=note,
                )
            )
            return Characterization(
                association=association,
                captured_at=captured_at,
                delta_seconds=delta,
                timestamp_source="characterization" if captured_at else "none",
                metrics=metrics or None,
            )

        evidence.append(
            Evidence(
                path="/characterization",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes="No backend properties snapshot available for this job.",
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
                    metrics.append(
                        CharacterizationMetric(
                            name=str(key), value=float(value), unit=_metric_unit(str(key))
                        )
                    )
        return metrics


__all__ = ["IBMProvenanceAdapter"]
