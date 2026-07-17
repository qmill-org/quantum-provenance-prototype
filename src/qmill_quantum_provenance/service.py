"""In-process provenance service with an in-memory record store.

This is the delivery form for the prototype: the two contract operations are
exposed as Python methods that the QAS FastAPI layer can wrap. No HTTP server
lives in this repository. Provider branching stays inside adapters; this class
only performs generic assembly (canonical envelope, application-captured
context, operation accounting) over an :class:`AdapterResult`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from .adapter import (
    AdapterResult,
    ApplicationCompilationContext,
    ApplicationSoftwareContext,
    CreateProvenanceRecordRequest,
    ProvenanceAdapter,
    ProvenanceCollectionRequest,
    SourceProgramInput,
)
from .models import (
    Adapter,
    Artifact,
    ArtifactRole,
    Compilation,
    ContentHash,
    Evidence,
    EvidenceStatus,
    MappingEntry,
    OperationObservation,
    ProvenanceRecord,
    SoftwareContext,
    canonical_job_id,
)
from .registry import ProvenanceAdapterRegistry, default_registry


_SOURCE_MEDIA_TYPES = {
    "openqasm3": "application/x-openqasm;version=3",
    "openqasm2": "application/x-openqasm;version=2",
    "qiskit-qpy": "application/x-qiskit-qpy",
    "braket-ir": "application/x-braket-ir+json",
}


class ProvenanceService:
    """Assemble and serve canonical provenance records in-process."""

    def __init__(
        self,
        registry: ProvenanceAdapterRegistry | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or default_registry()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._store: dict[str, ProvenanceRecord] = {}

    # -- contract operations -------------------------------------------------

    def create_record(
        self, request: CreateProvenanceRecordRequest
    ) -> tuple[ProvenanceRecord, bool]:
        """POST /v1/provenance-records. Returns ``(record, created)``."""

        canonical = canonical_job_id(request.provider, request.external_job_id, request.scope)
        existing = self._store.get(canonical)
        if existing is not None and not request.refresh:
            return existing, False

        adapter = self._registry.get(request.provider)
        collection = ProvenanceCollectionRequest(
            provider=request.provider,
            external_job_id=request.external_job_id,
            canonical_id=canonical,
            scope=request.scope,
            region=request.region,
        )
        result = adapter.collect(collection)
        record = self._assemble(canonical, request, adapter, result)
        self._store[canonical] = record
        return record, existing is None

    def get_provenance(self, job_id: str) -> ProvenanceRecord | None:
        """GET /v1/jobs/{job_id}/provenance. ``None`` -> 404 at the HTTP edge."""

        return self._store.get(job_id)

    # -- assembly ------------------------------------------------------------

    def _assemble(
        self,
        canonical: str,
        request: CreateProvenanceRecordRequest,
        adapter: ProvenanceAdapter,
        result: AdapterResult,
    ) -> ProvenanceRecord:
        now = self._clock()
        artifacts = list(result.artifacts)
        evidence = list(result.evidence)

        self._apply_source_program(request.source_program, artifacts, evidence)
        compilation = self._merge_compilation(
            result.compilation, request.compilation_context, evidence
        )
        software = self._merge_software(result.software, request.software_context, evidence)

        operations = list(result.operations)
        operations.append(OperationObservation(actor="qmill", operation="create_provenance_record"))

        return ProvenanceRecord(
            record_id=canonical,
            generated_at=now,
            retrieved_at=result.retrieved_at or now,
            adapter=Adapter(
                provider=adapter.provider,
                name=getattr(adapter, "name", type(adapter).__name__),
                version=getattr(adapter, "version", "0.1.0-prototype"),
            ),
            job=result.job,
            device=result.device,
            results=result.results,
            artifacts=artifacts,
            evidence=evidence,
            warnings=list(result.warnings),
            operations=operations,
            compilation=compilation,
            execution=result.execution,
            characterization=result.characterization,
            software=software,
        )

    def _apply_source_program(
        self,
        source: SourceProgramInput | None,
        artifacts: list[Artifact],
        evidence: list[Evidence],
    ) -> None:
        if source is None:
            return
        content_hash = (
            ContentHash(source.content_hash[0], source.content_hash[1])
            if source.content_hash
            else None
        )
        media_type = _SOURCE_MEDIA_TYPES.get(source.format, "text/plain")
        index = len(artifacts)
        artifacts.append(
            Artifact(
                role=ArtifactRole.SOURCE,
                media_type=media_type,
                description=f"Application-captured source program ({source.format})",
                reference=source.reference,
                content_hash=content_hash,
            )
        )
        evidence.append(
            Evidence(
                path=f"/artifacts/{index}",
                status=EvidenceStatus.APPLICATION_CAPTURED,
                notes="Source program supplied by the submitting application.",
            )
        )

    def _merge_compilation(
        self,
        provider: Compilation | None,
        app: ApplicationCompilationContext | None,
        evidence: list[Evidence],
    ) -> Compilation | None:
        if app is None:
            return provider
        base = provider or Compilation()
        app_mapping = (
            [
                MappingEntry(logical, physical)
                for logical, physical in app.logical_to_physical_mapping
            ]
            if app.logical_to_physical_mapping
            else None
        )
        pairs = (
            ("compiler_name", base.compiler_name, app.compiler_name),
            ("compiler_version", base.compiler_version, app.compiler_version),
            ("optimization_level", base.optimization_level, app.optimization_level),
            ("random_seed", base.random_seed, app.random_seed),
            (
                "logical_to_physical_mapping",
                base.logical_to_physical_mapping,
                app_mapping,
            ),
        )
        for name, provider_value, app_value in pairs:
            if provider_value is None and app_value is not None:
                evidence.append(
                    Evidence(
                        path=f"/compilation/{name}",
                        status=EvidenceStatus.APPLICATION_CAPTURED,
                    )
                )
        return Compilation(
            compiler_name=base.compiler_name or app.compiler_name,
            compiler_version=base.compiler_version or app.compiler_version,
            optimization_level=(
                base.optimization_level
                if base.optimization_level is not None
                else app.optimization_level
            ),
            random_seed=(base.random_seed if base.random_seed is not None else app.random_seed),
            logical_to_physical_mapping=base.logical_to_physical_mapping or app_mapping,
            native_gate_counts=base.native_gate_counts,
            depth=base.depth,
        )

    def _merge_software(
        self,
        provider: SoftwareContext | None,
        app: ApplicationSoftwareContext | None,
        evidence: list[Evidence],
    ) -> SoftwareContext | None:
        if app is None:
            return provider
        base = provider or SoftwareContext()
        pairs = (
            ("provider_client", base.provider_client, app.provider_client),
            (
                "provider_client_version",
                base.provider_client_version,
                app.provider_client_version,
            ),
            ("compiler_name", base.compiler_name, app.compiler_name),
            ("compiler_version", base.compiler_version, app.compiler_version),
            ("python_version", base.python_version, app.python_version),
            ("framework_versions", base.framework_versions, app.framework_versions),
        )
        for name, provider_value, app_value in pairs:
            if not provider_value and app_value:
                evidence.append(
                    Evidence(
                        path=f"/software/{name}",
                        status=EvidenceStatus.APPLICATION_CAPTURED,
                    )
                )
        return SoftwareContext(
            provider_client=base.provider_client or app.provider_client,
            provider_client_version=base.provider_client_version or app.provider_client_version,
            compiler_name=base.compiler_name or app.compiler_name,
            compiler_version=base.compiler_version or app.compiler_version,
            python_version=base.python_version or app.python_version,
            framework_versions=base.framework_versions or app.framework_versions,
        )


__all__ = ["ProvenanceService"]
