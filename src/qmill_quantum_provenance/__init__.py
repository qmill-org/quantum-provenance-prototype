"""Unified Quantum Provenance — research prototype (in-process module).

Public surface of the prototype. Two contract operations are exposed via
:class:`ProvenanceService`, mirroring the reduced OpenAPI contract:

- ``create_record`` -> POST /v1/provenance-records
- ``get_provenance`` -> GET /v1/jobs/{job_id}/provenance

Provider retrieval is performed by :class:`ProvenanceAdapter` implementations
selected through the :class:`ProvenanceAdapterRegistry`; the submission and
execution paths are untouched.
"""

from __future__ import annotations

from .adapter import (
    AdapterCapabilities,
    AdapterResult,
    ApplicationCompilationContext,
    ApplicationSoftwareContext,
    CreateProvenanceRecordRequest,
    ProvenanceAdapter,
    ProvenanceCollectionRequest,
    SourceProgramInput,
)
from .models import (
    SCHEMA_VERSION,
    ArtifactRole,
    AvailabilityReason,
    CharacterizationAssociation,
    EvidenceStatus,
    ProvenanceRecord,
    canonical_job_id,
)
from .registry import ProvenanceAdapterRegistry, default_registry
from .service import ProvenanceService

__all__ = [
    "SCHEMA_VERSION",
    "ProvenanceService",
    "ProvenanceAdapter",
    "ProvenanceAdapterRegistry",
    "default_registry",
    "CreateProvenanceRecordRequest",
    "ProvenanceCollectionRequest",
    "AdapterResult",
    "AdapterCapabilities",
    "SourceProgramInput",
    "ApplicationCompilationContext",
    "ApplicationSoftwareContext",
    "ProvenanceRecord",
    "EvidenceStatus",
    "AvailabilityReason",
    "ArtifactRole",
    "CharacterizationAssociation",
    "canonical_job_id",
]
