"""Canonical provenance domain model for the research prototype.

These dataclasses mirror the reduced OpenAPI contract at
``qmill_quantum_provenance/openapi.json`` (schema version
``0.1.0-prototype``). ``to_dict`` produces JSON that validates against the
``ProvenanceRecord`` schema. The contract JSON remains the source of truth;
this module is the typed, in-process representation used by the service and
provider adapters.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


SCHEMA_VERSION = "0.1.0-prototype"


class EvidenceStatus(str, Enum):
    """Provenance qualifier attached to a normalized field."""

    PROVIDER_SUPPLIED = "provider_supplied"
    AGGREGATOR_NORMALIZED = "aggregator_normalized"
    PROVIDER_PASSTHROUGH = "provider_passthrough"
    DERIVED = "derived"
    APPLICATION_CAPTURED = "application_captured"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    NOT_VERIFIABLE = "not_verifiable"


class AvailabilityReason(str, Enum):
    """Why a value is unavailable. Required when status is ``unavailable``."""

    NOT_EXPOSED_BY_PROVIDER = "not_exposed_by_provider"
    NOT_CAPTURED_BY_APPLICATION = "not_captured_by_application"
    AUTHENTICATION_SCOPE_INSUFFICIENT = "authentication_scope_insufficient"
    UPSTREAM_REQUEST_FAILED = "upstream_request_failed"
    INSUFFICIENT_SOURCE_DATA = "insufficient_source_data"
    DISCARDED_BY_RETENTION_POLICY = "discarded_by_retention_policy"
    EXPIRED_PROVIDER_ARTIFACT = "expired_provider_artifact"
    UNSUPPORTED_BY_ADAPTER = "unsupported_by_adapter"


class ArtifactRole(str, Enum):
    SOURCE = "source"
    SUBMITTED = "submitted"
    COMPILED = "compiled"
    EXECUTED = "executed"
    ENVIRONMENT = "environment"
    RESULT = "result"
    PROVIDER_NATIVE = "provider_native"


class CharacterizationAssociation(str, Enum):
    PROVIDER_LINKED = "provider_linked"
    CONFIGURATION_LINKED = "configuration_linked"
    TIMESTAMP_MATCHED = "timestamp_matched"
    NEAREST_AVAILABLE = "nearest_available"
    CURRENT_AT_RETRIEVAL = "current_at_retrieval"


JobStatus = str  # one of the enum values below
_JOB_STATUSES = {
    "created",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "unknown",
}
DeviceType = str  # "qpu" | "simulator" | "unknown"


def _compact(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` (absent optional fields)."""

    return {key: value for key, value in mapping.items() if value is not None}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def canonical_job_id(provider: str, external_job_id: str, scope: str | None = None) -> str:
    """Deterministic canonical ID.

    Prototype default: ``qprov:{provider}:{sha256(provider|external|scope)[:32]}``.
    Deterministic so repeated registration of the same external job is idempotent.
    """

    digest = hashlib.sha256(f"{provider}|{external_job_id}|{scope or ''}".encode()).hexdigest()[:32]
    return f"qprov:{provider}:{digest}"


def normalize_job_status(raw: str | None) -> str:
    if not raw:
        return "unknown"
    lowered = raw.strip().lower()
    mapping = {
        "completed": "completed",
        "done": "completed",
        "failed": "failed",
        "error": "failed",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "cancelling": "cancelled",
        "queued": "queued",
        "running": "running",
        "created": "created",
        "initialized": "created",
    }
    return mapping.get(lowered, "unknown")


def normalize_device_type(raw: str | None) -> str:
    if not raw:
        return "unknown"
    lowered = raw.strip().lower()
    if lowered in {"qpu", "simulator"}:
        return lowered
    return "unknown"


@dataclass(frozen=True)
class ContentHash:
    algorithm: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {"algorithm": self.algorithm, "value": self.value}


@dataclass(frozen=True)
class Evidence:
    path: str
    status: EvidenceStatus
    reason: AvailabilityReason | None = None
    source_paths: list[str] | None = None
    derivation: str | None = None
    provider_field: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "path": self.path,
                "status": self.status.value,
                "reason": self.reason.value if self.reason else None,
                "source_paths": self.source_paths or None,
                "derivation": self.derivation,
                "provider_field": self.provider_field,
                "notes": self.notes,
            }
        )


@dataclass(frozen=True)
class Artifact:
    role: ArtifactRole
    media_type: str
    description: str | None = None
    reference: str | None = None
    content_hash: ContentHash | None = None
    byte_size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "role": self.role.value,
                "media_type": self.media_type,
                "description": self.description,
                "reference": self.reference,
                "content_hash": self.content_hash.to_dict() if self.content_hash else None,
                "byte_size": self.byte_size,
            }
        )


@dataclass(frozen=True)
class Adapter:
    provider: str
    name: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "name": self.name, "version": self.version}


@dataclass(frozen=True)
class Job:
    canonical_id: str
    provider: str
    external_id: str
    status: str
    created_at: datetime | None = None
    ended_at: datetime | None = None
    shots: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "canonical_id": self.canonical_id,
                "provider": self.provider,
                "external_id": self.external_id,
                "status": self.status,
                "created_at": _iso(self.created_at),
                "ended_at": _iso(self.ended_at),
                "shots": self.shots,
            }
        )


@dataclass(frozen=True)
class Device:
    provider: str
    identifier: str
    name: str | None = None
    type: str | None = None
    qubit_count: int | None = None
    platform_provider: str | None = None
    hardware_provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "provider": self.provider,
                "identifier": self.identifier,
                "name": self.name,
                "type": self.type,
                "qubit_count": self.qubit_count,
                "platform_provider": self.platform_provider,
                "hardware_provider": self.hardware_provider,
            }
        )


@dataclass(frozen=True)
class MappingEntry:
    logical: int
    physical: int

    def to_dict(self) -> dict[str, Any]:
        return {"logical": self.logical, "physical": self.physical}


@dataclass(frozen=True)
class Compilation:
    compiler_name: str | None = None
    compiler_version: str | None = None
    optimization_level: int | None = None
    random_seed: int | None = None
    logical_to_physical_mapping: list[MappingEntry] | None = None
    native_gate_counts: dict[str, int] | None = None
    depth: int | None = None

    def to_dict(self) -> dict[str, Any]:
        mapping = (
            [entry.to_dict() for entry in self.logical_to_physical_mapping]
            if self.logical_to_physical_mapping
            else None
        )
        return _compact(
            {
                "compiler_name": self.compiler_name,
                "compiler_version": self.compiler_version,
                "optimization_level": self.optimization_level,
                "random_seed": self.random_seed,
                "logical_to_physical_mapping": mapping,
                "native_gate_counts": self.native_gate_counts or None,
                "depth": self.depth,
            }
        )

    def is_empty(self) -> bool:
        return not self.to_dict()


@dataclass(frozen=True)
class Execution:
    queue_duration_ms: int | None = None
    run_duration_ms: int | None = None
    total_duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "queue_duration_ms": self.queue_duration_ms,
                "run_duration_ms": self.run_duration_ms,
                "total_duration_ms": self.total_duration_ms,
            }
        )

    def is_empty(self) -> bool:
        return not self.to_dict()


@dataclass(frozen=True)
class CharacterizationMetric:
    name: str
    value: float
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({"name": self.name, "value": self.value, "unit": self.unit})


@dataclass(frozen=True)
class Characterization:
    association: CharacterizationAssociation
    captured_at: datetime | None = None
    metrics: list[CharacterizationMetric] | None = None

    def to_dict(self) -> dict[str, Any]:
        metrics = [metric.to_dict() for metric in self.metrics] if self.metrics else None
        return _compact(
            {
                "association": self.association.value,
                "captured_at": _iso(self.captured_at),
                "metrics": metrics,
            }
        )


@dataclass(frozen=True)
class Results:
    available: bool
    shots: int | None = None
    measurement_counts: dict[str, int] | None = None
    measurement_probabilities: dict[str, float] | None = None
    estimated_measurement_counts: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "available": self.available,
                "shots": self.shots,
                "measurement_counts": self.measurement_counts or None,
                "measurement_probabilities": self.measurement_probabilities or None,
                "estimated_measurement_counts": self.estimated_measurement_counts or None,
            }
        )


@dataclass(frozen=True)
class SoftwareContext:
    provider_client: str | None = None
    provider_client_version: str | None = None
    compiler_name: str | None = None
    compiler_version: str | None = None
    python_version: str | None = None
    framework_versions: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "provider_client": self.provider_client,
                "provider_client_version": self.provider_client_version,
                "compiler_name": self.compiler_name,
                "compiler_version": self.compiler_version,
                "python_version": self.python_version,
                "framework_versions": self.framework_versions or None,
            }
        )

    def is_empty(self) -> bool:
        return not self.to_dict()


@dataclass(frozen=True)
class Warning:
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class OperationObservation:
    actor: str  # "qmill" | "adapter" | "provider"
    operation: str
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"actor": self.actor, "operation": self.operation, "count": self.count}


@dataclass
class ProvenanceRecord:
    record_id: str
    generated_at: datetime
    retrieved_at: datetime
    adapter: Adapter
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
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "generated_at": _iso(self.generated_at),
            "retrieved_at": _iso(self.retrieved_at),
            "adapter": self.adapter.to_dict(),
            "job": self.job.to_dict(),
            "device": self.device.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "results": self.results.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "operations": [op.to_dict() for op in self.operations],
        }
        if self.compilation is not None and not self.compilation.is_empty():
            payload["compilation"] = self.compilation.to_dict()
        if self.execution is not None and not self.execution.is_empty():
            payload["execution"] = self.execution.to_dict()
        if self.characterization is not None:
            payload["characterization"] = self.characterization.to_dict()
        if self.software is not None and not self.software.is_empty():
            payload["software"] = self.software.to_dict()
        return payload


__all__ = [
    "SCHEMA_VERSION",
    "EvidenceStatus",
    "AvailabilityReason",
    "ArtifactRole",
    "CharacterizationAssociation",
    "ContentHash",
    "Evidence",
    "Artifact",
    "Adapter",
    "Job",
    "Device",
    "MappingEntry",
    "Compilation",
    "Execution",
    "CharacterizationMetric",
    "Characterization",
    "Results",
    "SoftwareContext",
    "Warning",
    "OperationObservation",
    "ProvenanceRecord",
    "canonical_job_id",
    "normalize_job_status",
    "normalize_device_type",
]
