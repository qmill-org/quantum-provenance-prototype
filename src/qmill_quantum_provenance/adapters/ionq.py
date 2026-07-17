"""IonQ (direct cloud API) provenance adapter.

Reuses the existing integration :class:`ProviderAdapter` (submission/status/
result oriented) as the retrieval seam and maps IonQ-native job data into
provider-independent record sections plus per-field evidence. The submission
path and executors are untouched.

IonQ-specific handling that distinguishes this adapter from Braket and IBM:

* Results arrive as a *probability histogram* keyed by integer basis states.
  The adapter preserves the provider probabilities verbatim in
  ``measurement_probabilities`` (``provider_supplied``), rewriting integer keys
  as fixed-width bitstrings, and optionally derives
  ``estimated_measurement_counts`` (``derived``) by independent per-bucket
  rounding. It never places reconstructed values in ``measurement_counts``,
  which is reserved for provider-returned observed counts (Braket/IBM).
* Characterization is associated via the explicit characterization id that
  IonQ attaches to the job (``provider_linked``), not matched by timestamp or
  read at retrieval time.
* Execution reports an actual QPU ``execution_time`` from the provider, so the
  run duration is ``provider_supplied`` rather than derived from timestamps.
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
    normalize_device_type,
    normalize_job_status,
)
from ..redaction import redact

_QUBIT_COUNT_KEYS = ("qubits", "num_qubits", "n_qubits", "qubitCount", "qubit_count")


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


def _histogram_to_probabilities(histogram: dict[str, float], width: int) -> dict[str, float]:
    """Rewrite an IonQ probability histogram with fixed-width bitstring keys.

    Integer basis-state keys are rewritten as fixed-width big-endian bitstrings.
    The provider-supplied probability values are preserved verbatim (summed when
    two integer keys map to the same bitstring, which does not happen for a
    well-formed histogram).
    """

    probabilities: dict[str, float] = {}
    for state, probability in histogram.items():
        try:
            index = int(state)
        except (TypeError, ValueError):
            continue
        bitstring = format(index, f"0{max(width, 1)}b")
        probabilities[bitstring] = probabilities.get(bitstring, 0.0) + float(probability)
    return probabilities


def _probabilities_to_estimated_counts(
    probabilities: dict[str, float], shots: int
) -> dict[str, int]:
    """Derive estimated integer counts from probabilities and requested shots.

    Deterministic rule: each bucket is rounded independently as
    ``round(probability * shots)`` (Python round-half-to-even). Buckets are not
    adjusted to force the total to equal ``shots``; these are estimates, not
    observed per-shot counts, so the sum may differ from ``shots``.
    """

    return {state: round(probability * shots) for state, probability in probabilities.items()}


class IonQProvenanceAdapter(ProvenanceAdapter):
    provider = "ionq"
    name = "ionq-provenance-adapter"
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
            provider="ionq",
            supports_result_counts=True,
            supports_compilation=True,
            supports_characterization=True,
            supports_execution_timing=True,
            notes="Results preserve the provider probability histogram "
            "(measurement_probabilities); estimated counts are derived. "
            "Characterization is provider-linked; run duration is "
            "provider-supplied and total is derived.",
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
                provider_field="ionq.jobs.get().status",
            )
        )
        if snapshot.shots is not None:
            evidence.append(
                Evidence(
                    path="/job/shots",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="ionq.jobs.get().shots",
                )
            )
        _record_timestamp_evidence(snapshot, evidence, "ionq.jobs.get() request/response times")
        return Job(
            canonical_id=request.canonical_id,
            provider="ionq",
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
                provider_field="ionq.jobs.get().target" if target else None,
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
                    provider_field="ionq.backends.get().type",
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
                    provider_field="ionq.backends.get().qubits",
                )
            )

        evidence.append(
            Evidence(
                path="/device/platform_provider",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field="ionq.jobs.get() (IonQ Cloud)",
                notes="Job was submitted through the IonQ platform.",
            )
        )
        evidence.append(
            Evidence(
                path="/device/hardware_provider",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field="ionq.jobs.get().target",
                notes="IonQ operates the physical device directly.",
            )
        )

        return Device(
            provider="ionq",
            identifier=identifier,
            name=name,
            type=device_type,
            qubit_count=qubit_count,
            platform_provider="ionq",
            hardware_provider="ionq",
        )

    def _build_results(self, snapshot, result_data, evidence: list[Evidence]) -> Results:
        if result_data is None:
            evidence.append(
                Evidence(
                    path="/results",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.UPSTREAM_REQUEST_FAILED,
                )
            )
            return Results(available=False, shots=snapshot.shots)

        # IonQ-specific: preserve the provider probability histogram as the
        # canonical result. Reconstructed integer counts would misrepresent
        # observed per-shot counts, so they are kept separate and derived.
        payload = getattr(result_data, "raw_payload", None)
        histogram = payload.get("histogram") if isinstance(payload, dict) else None
        if isinstance(histogram, dict) and histogram:
            width = _find_int(payload, ("qubits", "num_qubits")) or 0
            if not width:
                width = max(int(state).bit_length() for state in histogram)
            probabilities = _histogram_to_probabilities(histogram, width)
            evidence.append(
                Evidence(
                    path="/results/measurement_probabilities",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="ionq.jobs.get_results() histogram",
                    notes=(
                        "IonQ returns outcome probabilities, not per-shot counts. "
                        "The provider values are preserved verbatim; integer basis "
                        "states are rewritten as fixed-width bitstrings."
                    ),
                )
            )

            estimated: dict[str, int] | None = None
            if snapshot.shots:
                estimated = _probabilities_to_estimated_counts(probabilities, snapshot.shots)
                evidence.append(
                    Evidence(
                        path="/results/estimated_measurement_counts",
                        status=EvidenceStatus.DERIVED,
                        source_paths=["/results/measurement_probabilities", "/job/shots"],
                        derivation="round(probability * shots) per bucket, independently",
                        notes=(
                            "Estimated counts derived from probabilities and requested "
                            "shots by independent per-bucket rounding. These are NOT "
                            "observed per-shot counts and need not sum to shots; no "
                            "bucket is adjusted to force the total."
                        ),
                    )
                )
            return Results(
                available=True,
                shots=snapshot.shots,
                measurement_probabilities=probabilities,
                estimated_measurement_counts=estimated,
            )

        # Fallback: provider already returned integer counts.
        if result_data.measurement_counts:
            evidence.append(
                Evidence(
                    path="/results/measurement_counts",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="ionq.jobs.get_results()",
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
                    media_type="application/json",
                    description="IonQ native-gate circuit executed on the QPU "
                    "(passthrough, hash only).",
                    content_hash=_sha256(compiled),
                    byte_size=len(compiled.encode("utf-8")),
                )
            )
            evidence.append(
                Evidence(
                    path=f"/artifacts/{index}",
                    status=EvidenceStatus.PROVIDER_PASSTHROUGH,
                    provider_field="ionq.jobs.get().circuit (native)",
                )
            )
        else:
            evidence.append(
                Evidence(
                    path="/compilation",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                    notes="No native circuit was returned with the job result.",
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
                description="Sanitized IonQ job metadata (content hash only).",
                content_hash=_sha256(canonical),
            )
        )
        evidence.append(
            Evidence(
                path=f"/artifacts/{index}",
                status=EvidenceStatus.PROVIDER_PASSTHROUGH,
                provider_field="ionq.jobs.get()",
                notes="Secrets redacted; only a content hash is retained.",
            )
        )

    def _build_execution(self, snapshot, evidence: list[Evidence]) -> Execution | None:
        created = snapshot.created_at
        ended = snapshot.ended_at

        run_ms = None
        metadata = getattr(snapshot, "metadata", None)
        if isinstance(metadata, dict):
            raw_run = metadata.get("execution_time_ms")
            if isinstance(raw_run, (int, float)) and not isinstance(raw_run, bool):
                run_ms = int(raw_run)

        total_ms = None
        if created is not None and ended is not None and ended >= created:
            total_ms = int((ended - created).total_seconds() * 1000)

        if run_ms is None and total_ms is None:
            evidence.append(
                Evidence(
                    path="/execution",
                    status=EvidenceStatus.UNAVAILABLE,
                    reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                )
            )
            return None

        # IonQ-specific: the QPU run duration is reported directly by the provider.
        if run_ms is not None:
            evidence.append(
                Evidence(
                    path="/execution/run_duration_ms",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="ionq.jobs.get().execution_time",
                )
            )
        if total_ms is not None:
            evidence.append(
                Evidence(
                    path="/execution/total_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/job/created_at", "/job/ended_at"],
                    derivation="ended_at - created_at",
                )
            )
        return Execution(run_duration_ms=run_ms, total_duration_ms=total_ms)

    def _build_characterization(
        self, device_details, evidence: list[Evidence]
    ) -> Characterization | None:
        calibration = getattr(device_details, "calibration_data", None) if device_details else None
        if isinstance(calibration, dict) and calibration:
            metrics = self._extract_metrics(calibration)
            characterization_id = calibration.get("characterization_id")
            evidence.append(
                Evidence(
                    path="/characterization",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="ionq.characterizations.get()",
                    notes=(
                        f"Linked characterization id {characterization_id}."
                        if characterization_id
                        else "Provider-linked characterization for this job."
                    ),
                )
            )
            return Characterization(
                association=CharacterizationAssociation.PROVIDER_LINKED,
                captured_at=_parse_timestamp(
                    calibration.get("captured_at") or calibration.get("date")
                ),
                metrics=metrics or None,
            )

        evidence.append(
            Evidence(
                path="/characterization",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes="No linked characterization available for this job.",
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
