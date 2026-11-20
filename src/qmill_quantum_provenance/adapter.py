"""Provenance adapter interface (sibling to the integration ProviderAdapter).

A ``ProvenanceAdapter`` retrieves an already-executed provider job and maps its
native, provider-specific representation into provider-independent record
sections plus per-field evidence. It never modifies executors or the submission
path. The shared :class:`ProvenanceService` performs generic assembly; all
provider branching lives inside the concrete adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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


def qualify_missing_results(
    evidence: list[Evidence], job_status: str, error: ProviderIntegrationError | None
) -> None:
    """Replace a generic ``/results`` unavailability with the actual reason.

    A cancelled or failed job has no results to retrieve (``not_applicable``);
    a job still pending has none yet; otherwise the upstream error decides.
    """

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


__all__ = [
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
