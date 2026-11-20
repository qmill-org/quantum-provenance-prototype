"""Provenance adapter interface (sibling to the integration ProviderAdapter).

A ``ProvenanceAdapter`` retrieves an already-executed provider job and maps its
native, provider-specific representation into provider-independent record
sections plus per-field evidence. It never modifies executors or the submission
path. The shared :class:`ProvenanceService` performs generic assembly; all
provider branching lives inside the concrete adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from .integration import (
    AccessDeniedError,
    JobNotFoundError,
    ProviderIntegrationError,
    ResultUnavailableError,
)
from .models import (
    Artifact,
    ArtifactRole,
    AvailabilityReason,
    Characterization,
    Compilation,
    Device,
    Evidence,
    EvidenceStatus,
    Execution,
    Job,
    JobFailure,
    JobRelations,
    OperationObservation,
    Results,
    SoftwareContext,
    Warning,
    is_recognized_job_status,
)


@dataclass(frozen=True)
class SourceProgramInput:
    """Application-captured source program descriptor (no inline content)."""

    format: str
    reference: str | None = None
    content_hash: tuple[str, str] | None = None  # (algorithm, value)


@dataclass(frozen=True)
class ApplicationCompilationContext:
    compiler_name: str | None = None
    compiler_version: str | None = None
    optimization_level: int | None = None
    random_seed: int | None = None
    logical_to_physical_mapping: list[tuple[int, int]] | None = None


@dataclass(frozen=True)
class ApplicationSoftwareContext:
    provider_client: str | None = None
    provider_client_version: str | None = None
    compiler_name: str | None = None
    compiler_version: str | None = None
    python_version: str | None = None
    framework_versions: dict[str, str] | None = None


@dataclass(frozen=True)
class CreateProvenanceRecordRequest:
    """Input to :meth:`ProvenanceService.create_record`."""

    provider: str
    external_job_id: str
    scope: str | None = None
    refresh: bool = False
    region: str | None = None
    source_program: SourceProgramInput | None = None
    compilation_context: ApplicationCompilationContext | None = None
    software_context: ApplicationSoftwareContext | None = None
    experiment_id: str | None = None
    requested_shots: int | None = None


@dataclass(frozen=True)
class ProvenanceCollectionRequest:
    """What the service hands to an adapter to collect provider-native data."""

    provider: str
    external_job_id: str
    canonical_id: str
    scope: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class AdapterCapabilities:
    """Declared retrieval capabilities for a provider adapter."""

    provider: str
    supports_result_counts: bool = False
    supports_compilation: bool = False
    supports_characterization: bool = False
    supports_execution_timing: bool = False
    notes: str | None = None


@dataclass
class AdapterResult:
    """Provider-independent sections produced by an adapter.

    The adapter fills what it can retrieve and records evidence for every
    normalized field, including ``unavailable`` entries with a reason. The
    service adds the canonical envelope, application-captured context, and the
    QMill-level operation observation.
    """

    job: Job
    device: Device
    results: Results
    artifacts: list[Artifact] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    operations: list[OperationObservation] = field(default_factory=list)
    compilation: Compilation | None = None
    execution: Execution | None = None
    characterization: Characterization | None = None
    software: SoftwareContext | None = None
    extensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    retrieved_at: datetime | None = None


class ProvenanceAdapter(ABC):
    """Provider-specific provenance retrieval + normalization."""

    provider: str

    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Return the adapter's declared retrieval capabilities."""

    @abstractmethod
    def collect(self, request: ProvenanceCollectionRequest) -> AdapterResult:
        """Retrieve the provider job and map it to provider-independent sections."""


_NOT_RUN = {"cancelled", "failed"}
_PENDING = {"created", "queued", "running"}


def reason_for(error: Exception) -> AvailabilityReason:
    """Availability reason for a failed upstream operation."""

    if isinstance(error, JobNotFoundError):
        return AvailabilityReason.NOT_FOUND_BY_PROVIDER
    if isinstance(error, AccessDeniedError):
        return AvailabilityReason.AUTHENTICATION_SCOPE_INSUFFICIENT
    return AvailabilityReason.UPSTREAM_REQUEST_FAILED


def _explains_results(item: Evidence) -> bool:
    """An adapter's specific statement about absent results (not the generic default)."""

    return item.path == "/results" and (
        item.status is EvidenceStatus.NOT_APPLICABLE
        or (
            item.status is EvidenceStatus.UNAVAILABLE
            and item.reason
            not in (
                AvailabilityReason.UPSTREAM_REQUEST_FAILED,
                AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                None,
            )
        )
    )


def qualify_missing_results(
    evidence: list[Evidence], job_status: str, error: ProviderIntegrationError | None
) -> None:
    """Replace a generic ``/results`` unavailability with the actual reason.

    A cancelled or failed job has no results to retrieve (``not_applicable``);
    a job still pending has none yet; otherwise the upstream error decides.
    """

    if any(_explains_results(item) for item in evidence):
        return  # the adapter already explained why there are no results
    if job_status in _NOT_RUN:
        replacement = Evidence(
            path="/results",
            status=EvidenceStatus.NOT_APPLICABLE,
            notes=f"Job {job_status}; there are no results to retrieve.",
        )
    elif job_status in _PENDING or isinstance(error, ResultUnavailableError):
        replacement = Evidence(
            path="/results",
            status=EvidenceStatus.UNAVAILABLE,
            reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
            notes=f"Results not available for a job in state {job_status!r}.",
        )
    elif error is not None:
        replacement = Evidence(
            path="/results",
            status=EvidenceStatus.UNAVAILABLE,
            reason=reason_for(error),
            notes=str(error)[:200],
        )
    elif job_status == "completed":
        replacement = Evidence(
            path="/results",
            status=EvidenceStatus.UNAVAILABLE,
            reason=AvailabilityReason.UNSUPPORTED_BY_ADAPTER,
            notes="Result retrieved, but its format is not one this adapter maps.",
        )
    else:
        return
    evidence[:] = [item for item in evidence if item.path != "/results"]
    evidence.append(replacement)


RESULT_REPRESENTATIONS = (
    "/results/measurement_counts",
    "/results/measurement_probabilities",
    "/results/estimated_measurement_counts",
)


def mark_not_applicable(
    evidence: list[Evidence], paths: tuple[str, ...] | list[str], note: str
) -> None:
    """Declare result representations that this record does not use."""

    for path in paths:
        evidence.append(Evidence(path=path, status=EvidenceStatus.NOT_APPLICABLE, notes=note))


def estimate_counts(probabilities: dict[str, float], shots: int) -> dict[str, int]:
    """``round(p * shots)`` per outcome, independently; may not sum to ``shots``."""

    return {state: int(round(p * shots)) for state, p in probabilities.items()}


def characterization_applies(job_status: str, evidence: list[Evidence]) -> bool:
    """False (and records why) when the job never produced an execution to describe."""

    if job_status in _NOT_RUN:
        evidence.append(
            Evidence(
                path="/characterization",
                status=EvidenceStatus.NOT_APPLICABLE,
                notes=f"Job {job_status}; a device snapshot would not describe an execution.",
            )
        )
        return False
    return True


def delta_seconds(captured_at: datetime | None, job_created_at: datetime | None) -> float | None:
    if captured_at is None or job_created_at is None:
        return None
    return round((captured_at - job_created_at).total_seconds(), 3)


def relations_with_evidence(
    evidence: list[Evidence],
    *,
    exposed: bool,
    provider_field: str,
    relations: JobRelations | None = None,
    notes: str | None = None,
) -> JobRelations | None:
    """Record job-relation evidence and return the relations to emit.

    ``exposed`` says whether the provider has relation fields at all. A provider
    that exposes them but reports none for this job describes a standalone job
    (``not_applicable``); a provider without such fields leaves the relation
    unknown (``unavailable``).
    """

    if relations is not None and not relations.is_empty():
        evidence.append(
            Evidence(
                path="/job/relations",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field=provider_field,
                notes=notes,
            )
        )
        return relations
    if exposed:
        evidence.append(
            Evidence(
                path="/job/relations",
                status=EvidenceStatus.NOT_APPLICABLE,
                provider_field=provider_field,
                notes=notes
                or "Provider reports no session, batch or parent/child job; standalone job.",
            )
        )
    else:
        evidence.append(
            Evidence(
                path="/job/relations",
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes=notes or "Provider job record has no session, batch or parent/child field.",
            )
        )
    return None


def failure_with_evidence(
    evidence: list[Evidence],
    job_status: str,
    *,
    provider_field: str,
    code: Any = None,
    message: Any = None,
) -> JobFailure | None:
    """Record failure evidence; a failure applies only to a failed job."""

    if job_status != "failed":
        evidence.append(
            Evidence(
                path="/job/failure",
                status=EvidenceStatus.NOT_APPLICABLE,
                notes=f"Job {job_status}; no failure to report.",
            )
        )
        return None
    if code or message:
        evidence.append(
            Evidence(
                path="/job/failure",
                status=EvidenceStatus.PROVIDER_SUPPLIED,
                provider_field=provider_field,
            )
        )
        return JobFailure(
            code=str(code) if code else None, message=str(message) if message else None
        )
    evidence.append(
        Evidence(
            path="/job/failure",
            status=EvidenceStatus.UNAVAILABLE,
            reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
            notes="Job failed; provider gave no failure code or message.",
        )
    )
    return None


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _time_like(value: Any) -> bool:
    if value is None or isinstance(value, datetime) or _number(value):
        return True
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    return False


def clean_seam(snapshot, device, result, warnings: list[Warning]):
    """Drop provider values that are not of their documented type.

    A malformed value is treated as unavailable (with a warning) rather than
    passed on as provider-supplied or allowed to break the mapping.
    """

    problems: list[str] = []
    if snapshot.shots is not None and not (
        isinstance(snapshot.shots, int)
        and not isinstance(snapshot.shots, bool)
        and snapshot.shots >= 0
    ):
        problems.append(f"job shots {snapshot.shots!r}")
        snapshot = replace(snapshot, shots=None)
    for name in ("created_at", "ended_at"):
        if not _time_like(getattr(snapshot, name)):
            problems.append(f"job {name} {getattr(snapshot, name)!r}")
            snapshot = replace(snapshot, **{name: None})
    if result is not None:
        counts = result.measurement_counts or {}
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in counts.values()):
            problems.append("measurement counts with non-integer values")
            result = replace(result, measurement_counts={})
        payload = result.raw_payload
        if payload is not None and not isinstance(payload, dict):
            problems.append(f"result payload of type {type(payload).__name__}")
            result = replace(result, raw_payload=None)
        elif isinstance(payload, dict) and isinstance(payload.get("histogram"), dict):
            if not all(_number(p) for p in payload["histogram"].values()):
                problems.append("probability histogram with non-numeric values")
                result = replace(
                    result, raw_payload={k: v for k, v in payload.items() if k != "histogram"}
                )
    if device is not None and isinstance(device.calibration_data, dict):
        metrics = device.calibration_data.get("metrics") or {}
        if not all(_number(v) for v in metrics.values()):
            problems.append("characterization metrics with non-numeric values")
            device = replace(device, calibration_data=None)
    for problem in problems:
        warnings.append(
            Warning(
                "malformed_provider_value",
                f"{problem}: not the documented type; treated as unavailable.",
            )
        )
    return snapshot, device, result


def requalify_after_failure(
    evidence: list[Evidence],
    artifacts: list[Artifact],
    job_status: str,
    device_error: Exception | None,
    result_error: Exception | None,
) -> None:
    """State the retrieval failure, not "not exposed", for what a failed call would hold.

    Also records why the compiled artifact role is absent (CC-8).
    """

    def failed(path: str) -> Exception | None:
        if device_error is not None and (
            (path.startswith("/device/") and path != "/device/identifier")
            or path.startswith("/characterization")
        ):
            return device_error
        if (
            result_error is not None
            and job_status == "completed"
            and (path.startswith("/results") or path == "/execution/executed_shots")
        ):
            return result_error
        return None

    for index, item in enumerate(evidence):
        error = failed(item.path)
        if (
            error is not None
            and item.status is EvidenceStatus.UNAVAILABLE
            and item.reason
            in (
                AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                AvailabilityReason.INSUFFICIENT_SOURCE_DATA,
                AvailabilityReason.UPSTREAM_REQUEST_FAILED,
            )
        ):
            evidence[index] = replace(
                item, reason=reason_for(error), notes=f"Retrieval failed: {error}"[:200]
            )

    role = ArtifactRole.COMPILED
    if any(a.role is role for a in artifacts) or any(
        e.path == "/artifacts" and e.artifact_role is role for e in evidence
    ):
        return
    if job_status in _NOT_RUN:
        evidence.append(
            Evidence(
                path="/artifacts",
                artifact_role=role,
                status=EvidenceStatus.NOT_APPLICABLE,
                notes=f"Job {job_status}.",
            )
        )
    elif result_error is not None and job_status == "completed":
        evidence.append(
            Evidence(
                path="/artifacts",
                artifact_role=role,
                status=EvidenceStatus.UNAVAILABLE,
                reason=reason_for(result_error),
                notes="Result retrieval failed.",
            )
        )
    else:
        evidence.append(
            Evidence(
                path="/artifacts",
                artifact_role=role,
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes="The provider returns no compiled program for this job.",
            )
        )


def add_executed_shots(
    execution: Execution | None,
    evidence: list[Evidence],
    job_status: str,
    value: int | None,
    *,
    status: EvidenceStatus = EvidenceStatus.PROVIDER_SUPPLIED,
    provider_field: str | None = None,
    source_paths: list[str] | None = None,
    derivation: str | None = None,
    notes: str | None = None,
    missing: EvidenceStatus = EvidenceStatus.UNAVAILABLE,
) -> Execution | None:
    """Record executed shots, kept apart from the requested ``job.shots``."""

    path = "/execution/executed_shots"
    if value is not None:
        evidence.append(
            Evidence(
                path=path,
                status=status,
                provider_field=provider_field,
                source_paths=source_paths,
                derivation=derivation,
                notes=notes,
            )
        )
        return replace(execution or Execution(), executed_shots=int(value))
    if job_status in _NOT_RUN or job_status in _PENDING:
        evidence.append(
            Evidence(path=path, status=EvidenceStatus.NOT_APPLICABLE, notes=f"Job {job_status}.")
        )
    elif missing is EvidenceStatus.NOT_APPLICABLE:
        evidence.append(Evidence(path=path, status=missing, notes=notes))
    else:
        evidence.append(
            Evidence(
                path=path,
                status=EvidenceStatus.UNAVAILABLE,
                reason=AvailabilityReason.NOT_EXPOSED_BY_PROVIDER,
                notes=notes or "Provider reports no executed-shot count separate from the request.",
            )
        )
    return execution


@dataclass(frozen=True)
class ExpectedField:
    """A provider field an adapter maps, with its accepted names (newest first).

    Older names stay accepted so a provider interface change does not break the
    mapping; when none of the names is present for a job in ``statuses`` the
    adapter warns instead of silently reporting the attribute ``unavailable``.
    """

    record_path: str
    names: tuple[str, ...]
    statuses: frozenset[str] = frozenset({"completed"})


DRIFT_WARNING_CODES = frozenset(
    {
        "expected_provider_field_missing",
        "unrecognized_result_format",
        "unrecognized_provider_schema",
        "unrecognized_provider_status",
    }
)


def read_field(metadata: Any, field: ExpectedField) -> tuple[Any, str | None]:
    """Value and matched name of the first accepted name present in ``metadata``."""

    if isinstance(metadata, dict):
        for name in field.names:
            if name in metadata:
                return metadata[name], name
    return None, None


def check_expected_fields(
    metadata: Any,
    fields: tuple[ExpectedField, ...],
    job_status: str,
    warnings: list[Warning],
) -> None:
    """Warn for mapped fields absent from the provider response.

    A key that is present with a null value is the provider saying "no value";
    only a missing key suggests the interface changed.
    """

    for expected in fields:
        if job_status not in expected.statuses:
            continue
        if read_field(metadata, expected)[1] is None:
            warnings.append(
                Warning(
                    "expected_provider_field_missing",
                    f"{expected.record_path}: none of {', '.join(expected.names)} in the provider "
                    f"response for a {job_status} job; reported unavailable. The provider "
                    "interface may have changed.",
                )
            )


def check_status_recognized(raw: str | None, warnings: list[Warning]) -> None:
    """Warn when the provider reports a job state the normalizer does not know."""

    if raw and not is_recognized_job_status(raw):
        warnings.append(
            Warning(
                "unrecognized_provider_status",
                f"Provider job status {raw!r} is not a known state; job.status reported "
                "unknown. The provider interface may have changed.",
            )
        )


def check_result_recognized(
    job_status: str,
    result_retrieved: bool,
    results: Results,
    warnings: list[Warning],
    evidence: list[Evidence] | None = None,
) -> None:
    """Warn when a completed job's result was retrieved but not understood."""

    explained = any(_explains_results(item) for item in evidence or [])
    if job_status == "completed" and result_retrieved and not results.available and not explained:
        warnings.append(
            Warning(
                "unrecognized_result_format",
                "Result retrieved for a completed job, but it holds no result "
                "representation this adapter maps; reported unavailable.",
            )
        )


__all__ = [
    "clean_seam",
    "requalify_after_failure",
    "add_executed_shots",
    "check_expected_fields",
    "check_status_recognized",
    "check_result_recognized",
    "DRIFT_WARNING_CODES",
    "ExpectedField",
    "read_field",
    "characterization_applies",
    "failure_with_evidence",
    "relations_with_evidence",
    "delta_seconds",
    "RESULT_REPRESENTATIONS",
    "mark_not_applicable",
    "estimate_counts",
    "reason_for",
    "qualify_missing_results",
    "SourceProgramInput",
    "ApplicationCompilationContext",
    "ApplicationSoftwareContext",
    "CreateProvenanceRecordRequest",
    "ProvenanceCollectionRequest",
    "AdapterCapabilities",
    "AdapterResult",
    "ProvenanceAdapter",
]
