"""Minimal provider-integration interface for the provenance artifact.

This module is a self-contained copy of the small surface the provenance
prototype depends on from ``qmill_common.quantum_providers.integration`` in the
original codebase (PR #25 on ``qmill-org/common``). Only the abstract
:class:`ProviderAdapter` contract, the canonical data models, and the
``ResultUnavailableError`` used by the offline replay flow are reproduced here so
the artifact is independently runnable without the private ``qmill_common``
package.

The submission-oriented models (:class:`TargetInfo`, :class:`ResolvedTarget`,
:class:`SubmissionResult`) are present only to complete the adapter contract;
the artifact's replay path exercises the retrieval methods exclusively.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


# --- errors -----------------------------------------------------------------


class ProviderIntegrationError(Exception):
    """Base class for integration-layer failures."""


class ResultUnavailableError(ProviderIntegrationError):
    """Raised when a task result is not yet available."""


# --- canonical data models --------------------------------------------------

TargetType = Literal["SIMULATOR", "QPU"]
TargetStatus = Literal["ONLINE", "OFFLINE", "UNKNOWN"]


@dataclass(frozen=True)
class TargetInfo:
    provider: str
    target_id: str
    provider_target_id: str
    name: str
    type: TargetType
    status: TargetStatus
    region: str | None
    capabilities: list[str]


@dataclass(frozen=True)
class ResolvedTarget:
    provider: str
    target_id: str
    provider_target_id: str
    region: str


@dataclass(frozen=True)
class SubmissionResult:
    provider: str
    provider_job_id: str
    status: str
    submitted_at: datetime | None


@dataclass(frozen=True)
class DeviceDetails:
    provider: str
    target_id: str
    provider_target_id: str | None
    name: str | None
    type: str | None
    status: str | None
    calibration_data: dict[str, Any] | None
    provider_properties: dict[str, Any] | None
    metadata: dict[str, Any] | None


@dataclass
class TaskHandle:
    provider: str
    provider_job_id: str
    region: str | None = None
    target_id: str | None = None
    provider_target_id: str | None = None
    raw_task: Any | None = None


@dataclass(frozen=True)
class TaskSnapshot:
    provider: str
    provider_job_id: str
    status: str
    created_at: datetime | None
    ended_at: datetime | None
    shots: int | None
    target_id: str | None
    provider_target_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskResult:
    provider: str
    provider_job_id: str
    status: str
    measurement_counts: dict[str, int]
    compiled_circuit: str | None
    compiled_circuit_metrics: dict[str, Any] | None
    raw_payload: dict[str, Any] | None


# --- adapter contract -------------------------------------------------------


class ProviderAdapter(ABC):
    """Provider-agnostic adapter contract used by the provenance service."""

    @abstractmethod
    def list_targets(self, region: str | None = None) -> list[TargetInfo]:
        """List canonical targets for a provider."""

    @abstractmethod
    def resolve_target(self, target_id: str, region: str | None = None) -> ResolvedTarget:
        """Resolve a user-supplied target identifier to a provider-native target."""

    @abstractmethod
    def get_device_details(self, target_id: str, region: str | None = None) -> DeviceDetails:
        """Fetch canonical device inspection details for a target."""

    @abstractmethod
    def submit_openqasm(
        self,
        openqasm: str,
        shots: int,
        target: ResolvedTarget,
        s3_bucket: str | None = None,
        s3_prefix: str | None = None,
    ) -> SubmissionResult:
        """Submit an OpenQASM program for execution."""

    @abstractmethod
    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        """Construct a task handle from a provider job identifier."""

    @abstractmethod
    def get_status(self, task: TaskHandle) -> TaskSnapshot:
        """Fetch canonical task status metadata."""

    @abstractmethod
    def get_result(self, task: TaskHandle) -> TaskResult:
        """Fetch canonical task results."""

    @abstractmethod
    def get_compiled_circuit(self, task: TaskHandle) -> str | None:
        """Fetch compiled circuit text when available."""


__all__ = [
    "ProviderIntegrationError",
    "ResultUnavailableError",
    "TargetInfo",
    "ResolvedTarget",
    "SubmissionResult",
    "DeviceDetails",
    "TaskHandle",
    "TaskSnapshot",
    "TaskResult",
    "ProviderAdapter",
]
