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

from ..integration import ProviderAdapter, ProviderIntegrationError
from ..adapter import (
    clean_seam,
    requalify_after_failure,
    check_status_recognized,
    add_executed_shots,
    check_expected_fields,
    check_result_recognized,
    ExpectedField,
    read_field,
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


_EXPECTED_FIELDS = (
    # v0.4 renamed execution_time_ms (v0.3) to execution_duration_ms.
    ExpectedField("/execution/run_duration_ms", ("execution_duration_ms", "execution_time_ms")),
)


SIMULATION_NAMESPACE = "simulation.ionq"


def _simulation_extension(
    metadata: dict[str, Any] | None, device_type: str, evidence: list[Evidence]
) -> dict[str, Any]:
    """Noise model and seed of a simulator job (F13); no core field holds them."""

    noise = (metadata or {}).get("noise")
    if device_type != "simulator" or not isinstance(noise, dict) or not noise.get("model"):
        return {}
    simulation = {"noise_model": noise["model"]}
    if noise.get("seed") is not None:
        simulation["seed"] = noise["seed"]
    evidence.append(
        Evidence(
            path=f"/extensions/{SIMULATION_NAMESPACE}",
            status=EvidenceStatus.PROVIDER_SUPPLIED,
            provider_field="job noise.model / noise.seed",
            notes="'ideal' is exact simulation; other models emulate the named QPU's noise.",
        )
    )
    return {SIMULATION_NAMESPACE: simulation}


class IonQProvenanceAdapter(ProvenanceAdapter):
    provider = "ionq"
    name = "ionq-provenance-adapter"
    version = "0.2.0"

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
        device_error: Exception | None = None
        device_details = None
        if target:
            try:
                device_details = integration.get_device_details(target, region=request.region)
                operations.append(OperationObservation("adapter", "get_device_details"))
            except Exception as exc:  # provider/lookup failure is non-fatal
                device_error = exc
                warnings.append(Warning("device_details_unavailable", str(exc)))

        result_data = None
        result_error: ProviderIntegrationError | None = None
        try:
            result_data = integration.get_result(handle)
            operations.append(OperationObservation("adapter", "get_result"))
        except ProviderIntegrationError as exc:
            result_error = exc
            warnings.append(Warning("results_unavailable", str(exc)))

        snapshot, device_details, result_data = clean_seam(
            snapshot, device_details, result_data, warnings
        )
        job = self._build_job(request, snapshot, evidence)
        device = self._build_device(target, device_details, evidence)
        results = self._build_results(snapshot, result_data, evidence)
        if not results.available:
            qualify_missing_results(evidence, job.status, result_error)
        check_result_recognized(job.status, result_data is not None, results, warnings, evidence)
        check_status_recognized(snapshot.status, warnings)
        check_expected_fields(snapshot.metadata, _EXPECTED_FIELDS, job.status, warnings)
        self._build_compiled_artifact(result_data, artifacts, evidence)
        self._build_provider_native_artifact(snapshot, artifacts, evidence)
        execution = self._build_execution(snapshot, evidence)
        noise = (snapshot.metadata or {}).get("noise") or {}
        ideal = isinstance(noise, dict) and noise.get("model") == "ideal"
        execution = add_executed_shots(
            execution,
            evidence,
            job.status,
            None,
            missing=EvidenceStatus.NOT_APPLICABLE if ideal else EvidenceStatus.UNAVAILABLE,
            notes=(
                "Ideal simulation: exact probabilities, no shots executed."
                if ideal
                else "IonQ reports the requested shots only."
            ),
        )
        characterization = self._build_characterization(device_details, snapshot, job, evidence)
        extensions = _simulation_extension(snapshot.metadata, device.type, evidence)

        requalify_after_failure(evidence, artifacts, job.status, device_error, result_error)
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
            extensions=extensions,
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
        metadata = snapshot.metadata or {}
        failure_info = metadata.get("failure") or {}
        if not isinstance(failure_info, dict):
            failure_info = {"message": failure_info}
        relations = relations_with_evidence(
            evidence,
            exposed=any(k in metadata for k in ("session_id", "parent_job_id", "child_job_ids")),
            provider_field="v0.4 job session_id / parent_job_id / child_job_ids",
            relations=JobRelations(
                session_id=metadata.get("session_id"),
                parent_job_id=metadata.get("parent_job_id"),
                child_job_ids=list(metadata.get("child_job_ids") or []) or None,
            ),
        )
        failure = failure_with_evidence(
            evidence,
            status,
            provider_field="job failure.code / failure.message",
            code=failure_info.get("code"),
            message=failure_info.get("message") or failure_info.get("error"),
        )
        return Job(
            canonical_id=request.canonical_id,
            provider="ionq",
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

        payload = getattr(result_data, "raw_payload", None)
        if isinstance(payload, dict) and "per_child_probabilities" in payload:
            evidence.append(
                Evidence(
                    path="/results",
                    status=EvidenceStatus.NOT_APPLICABLE,
                    provider_field="results.probabilities.url (aggregated, keyed by child job)",
                    notes="Multi-circuit job: each circuit's result belongs to a child job "
                    "(job.relations.child_job_ids); see those jobs' records.",
                )
            )
            mark_not_applicable(
                evidence, RESULT_REPRESENTATIONS, "Multi-circuit parent job; see child jobs."
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

            mark_not_applicable(
                evidence,
                ["/results/measurement_counts"],
                "IonQ returns probabilities, not per-shot counts.",
            )
            estimated: dict[str, int] | None = None
            if not snapshot.shots:
                evidence.append(
                    Evidence(
                        path="/results/estimated_measurement_counts",
                        status=EvidenceStatus.UNAVAILABLE,
                        reason=AvailabilityReason.INSUFFICIENT_SOURCE_DATA,
                        notes="The job reports no shot count, so counts cannot be estimated.",
                    )
                )
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
                outcome_basis="bitstring",
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
            mark_not_applicable(
                evidence,
                RESULT_REPRESENTATIONS[1:],
                "Provider returned integer counts.",
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
            index = len(artifacts)
            artifacts.append(
                Artifact(
                    role=ArtifactRole.COMPILED,
                    media_type="application/json",
                    producer="provider",
                    description="IonQ native-gate circuit executed on the QPU "
                    "(passthrough, hash only).",
                    content_hash=ContentHash("sha256", program_digest(compiled)[0]),
                    byte_size=program_digest(compiled)[1],
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
        raw_run, run_field = read_field(getattr(snapshot, "metadata", None), _EXPECTED_FIELDS[0])
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
                    provider_field=f"ionq.jobs.get().{run_field}",
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
        self, device_details, snapshot, job, evidence: list[Evidence]
    ) -> Characterization | None:
        if not characterization_applies(job.status, evidence):
            return None
        calibration = getattr(device_details, "calibration_data", None) if device_details else None
        if not calibration and str(getattr(device_details, "type", "")).upper() == "SIMULATOR":
            evidence.append(
                Evidence(
                    path="/characterization",
                    status=EvidenceStatus.NOT_APPLICABLE,
                    notes="Simulator; no hardware characterization (a noise model, if used, "
                    f"is in /extensions/{SIMULATION_NAMESPACE}).",
                )
            )
            return None
        if isinstance(calibration, dict) and calibration:
            metrics = self._extract_metrics(calibration)
            captured_at = _parse_timestamp(
                calibration.get("captured_at") or calibration.get("date")
            )
            characterization_id = calibration.get("characterization_id")
            job_link = (snapshot.metadata or {}).get("characterization_id")
            if characterization_id and job_link == characterization_id:
                association = CharacterizationAssociation.PROVIDER_LINKED
                note = f"Job names characterization {characterization_id} (API v0.3 field)."
                granularity = None
            elif calibration.get("query") == "latest_at_or_before_submission":
                association = CharacterizationAssociation.TIMESTAMP_MATCHED
                note = (
                    f"Latest daily characterization at or before submission ({characterization_id}); "
                    "API v0.4 jobs carry no characterization identifier."
                )
                granularity = "day"
            else:
                association = CharacterizationAssociation.CURRENT_AT_RETRIEVAL
                note = "Characterization not linked to the job by the provider."
                granularity = None
            evidence.append(
                Evidence(
                    path="/characterization",
                    status=EvidenceStatus.PROVIDER_SUPPLIED,
                    provider_field="ionq characterizations",
                    notes=note,
                )
            )
            return Characterization(
                association=association,
                captured_at=captured_at,
                delta_seconds=delta_seconds(captured_at, job.created_at),
                timestamp_source="characterization" if captured_at else "none",
                timestamp_granularity=granularity,
                metrics=metrics or None,
            )

        evidence.append(
            Evidence(
                path="/characterization",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes="No characterization available for this job.",
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
