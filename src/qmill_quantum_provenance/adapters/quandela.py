"""Quandela Cloud provenance adapter (photonic, linear-optical).

Written under the new-provider protocol (``protocols/new-provider-quandela.md``)
from the mapping table in ``protocols/quandela-mapping.md``. Photonic
structure without a core field goes to ``extensions["photonic.quandela"]``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..adapter import (
    RESULT_REPRESENTATIONS,
    mark_not_applicable,
    qualify_missing_results,
    AdapterCapabilities,
    AdapterResult,
    ProvenanceAdapter,
    ProvenanceCollectionRequest,
)
from ..integration import ProviderAdapter, ProviderIntegrationError
from ..redaction import program_digest
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

NAMESPACE = "photonic.quandela"


def _parse(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    return None


def _supplied(path: str, field: str, notes: str | None = None) -> Evidence:
    return Evidence(
        path=path, status=EvidenceStatus.PROVIDER_SUPPLIED, provider_field=field, notes=notes
    )


def _unavailable(path: str, reason: AvailabilityReason, notes: str | None = None) -> Evidence:
    return Evidence(path=path, status=EvidenceStatus.UNAVAILABLE, reason=reason, notes=notes)


class QuandelaProvenanceAdapter(ProvenanceAdapter):
    provider = "quandela"
    name = "quandela-provenance-adapter"
    version = "0.2.0-dev"

    def __init__(self, integration_adapter: ProviderAdapter | None = None) -> None:
        self._integration = integration_adapter

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            provider="quandela",
            supports_result_counts=True,
            supports_compilation=True,
            supports_characterization=True,
            supports_execution_timing=True,
            notes="Fock-state sample counts; provider-compiled experiment; untimed platform perfs.",
        )

    def collect(self, request: ProvenanceCollectionRequest) -> AdapterResult:
        if self._integration is None:
            raise NotImplementedError("Supply a live or replay integration adapter.")
        integration = self._integration
        evidence: list[Evidence] = []
        warnings: list[Warning] = []
        artifacts: list[Artifact] = []
        operations: list[OperationObservation] = []
        extension: dict[str, Any] = {}

        handle = integration.get_task(request.external_job_id, region=request.region)
        operations.append(OperationObservation("adapter", "get_task"))
        snapshot = integration.get_status(handle)
        operations.append(OperationObservation("adapter", "get_status"))
        platform = snapshot.provider_target_id or snapshot.target_id

        device_details = None
        if platform:
            try:
                device_details = integration.get_device_details(platform)
                operations.append(OperationObservation("adapter", "get_device_details"))
            except Exception as exc:
                warnings.append(Warning("device_details_unavailable", str(exc)))

        result = None
        result_error: ProviderIntegrationError | None = None
        try:
            result = integration.get_result(handle)
            operations.append(OperationObservation("adapter", "get_result"))
        except ProviderIntegrationError as exc:
            result_error = exc
            warnings.append(Warning("results_unavailable", str(exc)))

        metadata = snapshot.metadata or {}
        job = self._job(request, snapshot, metadata, evidence)
        device = self._device(platform, device_details, evidence, extension)
        results = self._results(result, evidence, extension)
        if not results.available:
            qualify_missing_results(evidence, job.status, result_error)
        self._compiled(result, artifacts, evidence, extension)
        execution = self._execution(metadata, evidence)
        characterization = self._characterization(device, device_details, evidence, extension)

        if extension:
            evidence.append(
                _supplied(f"/extensions/{NAMESPACE}", "platform specs, job status and result")
            )
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
            extensions={NAMESPACE: extension} if extension else {},
            retrieved_at=datetime.now(UTC),
        )

    def _job(self, request, snapshot, metadata, evidence: list[Evidence]) -> Job:
        created = _parse(snapshot.created_at)
        start, duration = _parse(metadata.get("start_time")), metadata.get("duration")
        ended = (
            start + timedelta(seconds=duration)
            if start and isinstance(duration, (int, float))
            else None
        )
        evidence.append(_supplied("/job/status", "job status.status"))
        if created:
            evidence.append(_supplied("/job/created_at", "job status.creation_datetime"))
        else:
            evidence.append(
                _unavailable("/job/created_at", AvailabilityReason.NOT_EXPOSED_BY_PROVIDER)
            )
        if ended:
            evidence.append(
                Evidence(
                    path="/job/ended_at",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["job status.start_time", "job status.duration"],
                    derivation="start_time + duration (duration in whole seconds)",
                )
            )
        else:
            evidence.append(
                _unavailable("/job/ended_at", AvailabilityReason.NOT_EXPOSED_BY_PROVIDER)
            )
        if snapshot.shots is not None:
            evidence.append(
                _supplied(
                    "/job/shots", "job status.shots", "photon-detection shots, not accepted samples"
                )
            )
        return Job(
            canonical_id=request.canonical_id,
            provider="quandela",
            external_id=request.external_job_id,
            status=normalize_job_status(snapshot.status),
            created_at=created,
            ended_at=ended,
            shots=snapshot.shots,
        )

    def _device(self, platform, details, evidence: list[Evidence], extension: dict) -> Device:
        evidence.append(
            Evidence(
                path="/device/identifier",
                status=EvidenceStatus.APPLICATION_CAPTURED,
                notes="Job status and result do not name the platform; taken from the job reference.",
            )
        )
        evidence.append(_supplied("/device/platform_provider", "api.cloud.quandela.com"))
        evidence.append(_supplied("/device/hardware_provider", "api.cloud.quandela.com"))
        evidence.append(
            Evidence(
                path="/device/qubit_count",
                status=EvidenceStatus.NOT_APPLICABLE,
                notes=f"Photonic platform: capacity in modes and photons, see /extensions/{NAMESPACE}.",
            )
        )
        device_type = normalize_device_type(details.type) if details else "unknown"
        if device_type != "unknown":
            evidence.append(_supplied("/device/type", "platform.type"))
        else:
            evidence.append(
                _unavailable("/device/type", AvailabilityReason.UPSTREAM_REQUEST_FAILED)
            )
        properties = (details.provider_properties or {}) if details else {}
        if properties:
            extension["platform"] = {k: v for k, v in properties.items() if v is not None}
        return Device(
            provider="quandela",
            identifier=platform or "unknown",
            name=details.name if details else None,
            type=device_type,
            platform_provider="quandela_cloud",
            hardware_provider="quandela",
        )

    def _results(self, result, evidence: list[Evidence], extension: dict) -> Results:
        if result is None or not result.measurement_counts:
            evidence.append(_unavailable("/results", AvailabilityReason.NOT_EXPOSED_BY_PROVIDER))
            return Results(available=False)
        evidence.append(
            _supplied("/results/measurement_counts", "job result BSCount", "keys are Fock states")
        )
        evidence.append(_supplied("/results/outcome_basis", "job result BSCount"))
        mark_not_applicable(
            evidence,
            RESULT_REPRESENTATIONS[1:],
            "sample_count job: observed Fock-state counts, no probabilities.",
        )
        payload = result.raw_payload or {}
        extension["sampling"] = {
            k: payload[k]
            for k in ("shots", "physical_perf", "logical_perf", "global_perf", "duration")
            if k in payload
        }
        extension["sampling"]["accepted_samples"] = sum(result.measurement_counts.values())
        if payload.get("intermediate_results") is not None:
            extension["intermediate_results_count"] = len(payload["intermediate_results"])
        return Results(
            available=True,
            measurement_counts=dict(result.measurement_counts),
            outcome_basis="fock_state",
        )

    def _compiled(
        self, result, artifacts: list[Artifact], evidence: list[Evidence], extension
    ) -> None:
        compiled = result.compiled_circuit if result is not None else None
        if not compiled:
            evidence.append(
                _unavailable("/compilation", AvailabilityReason.NOT_EXPOSED_BY_PROVIDER)
            )
            return
        artifacts.append(
            Artifact(
                role=ArtifactRole.COMPILED,
                media_type="application/x-perceval-serialized",
                producer="provider",
                description="Experiment as compiled by the provider onto the chip (hash only).",
                content_hash=ContentHash("sha256", program_digest(compiled)[0]),
                byte_size=program_digest(compiled)[1],
            )
        )
        evidence.append(
            _supplied(f"/artifacts/{len(artifacts) - 1}", "job result.computed_experiment")
        )
        modes = (result.compiled_circuit_metrics or {}).get("modes")
        if modes:
            extension["compiled_modes"] = modes

    def _execution(self, metadata, evidence: list[Evidence]) -> Execution | None:
        created = _parse(metadata.get("creation_datetime"))
        start = _parse(metadata.get("start_time"))
        duration = metadata.get("duration")
        if start is None or not isinstance(duration, (int, float)):
            evidence.append(_unavailable("/execution", AvailabilityReason.NOT_EXPOSED_BY_PROVIDER))
            return None
        run_ms = int(duration * 1000)
        evidence.append(
            _supplied("/execution/run_duration_ms", "job status.duration", "whole seconds")
        )
        queue_ms = None
        if created is not None and start >= created:
            queue_ms = int((start - created).total_seconds() * 1000)
            evidence.append(
                Evidence(
                    path="/execution/queue_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["job status.creation_datetime", "job status.start_time"],
                    derivation="start_time - creation_datetime",
                )
            )
        total_ms = queue_ms + run_ms if queue_ms is not None else None
        if total_ms is not None:
            evidence.append(
                Evidence(
                    path="/execution/total_duration_ms",
                    status=EvidenceStatus.DERIVED,
                    source_paths=["/execution/queue_duration_ms", "/execution/run_duration_ms"],
                    derivation="queue + run",
                )
            )
        return Execution(
            queue_duration_ms=queue_ms, run_duration_ms=run_ms, total_duration_ms=total_ms
        )

    def _characterization(
        self, device, details, evidence: list[Evidence], extension
    ) -> Characterization | None:
        if device.type == "simulator":
            evidence.append(
                Evidence(
                    path="/characterization",
                    status=EvidenceStatus.NOT_APPLICABLE,
                    notes="Simulated platform; no hardware characterization.",
                )
            )
            return None
        calibration = details.calibration_data if details else None
        if not calibration:
            evidence.append(
                _unavailable("/characterization", AvailabilityReason.NOT_EXPOSED_BY_PROVIDER)
            )
            return None
        evidence.append(
            _supplied(
                "/characterization",
                "platform.perfs",
                "Platform perfs carry no observation timestamp.",
            )
        )
        arrays = {
            k: calibration[k]
            for k in ("per_mode_transmission", "dark_counts_per_detector")
            if calibration.get(k) is not None
        }
        if arrays:
            extension["characterization"] = arrays
        metrics = [
            CharacterizationMetric(
                name=name.split("[")[0], value=value, unit=name.split("[")[1].rstrip("]")
            )
            for name, value in (calibration.get("metrics") or {}).items()
        ]
        return Characterization(
            association=CharacterizationAssociation.CURRENT_AT_RETRIEVAL,
            captured_at=None,
            metrics=metrics or None,
        )


__all__ = ["QuandelaProvenanceAdapter", "NAMESPACE"]
