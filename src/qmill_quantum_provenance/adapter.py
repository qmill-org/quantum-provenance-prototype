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

from .models import (
    Artifact,
    Characterization,
    Compilation,
    Device,
    Evidence,
    Execution,
    Job,
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


__all__ = [
    "SourceProgramInput",
    "ApplicationCompilationContext",
    "ApplicationSoftwareContext",
    "CreateProvenanceRecordRequest",
    "ProvenanceCollectionRequest",
    "AdapterCapabilities",
    "AdapterResult",
    "ProvenanceAdapter",
]
