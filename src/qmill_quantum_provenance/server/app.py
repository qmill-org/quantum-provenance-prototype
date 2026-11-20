"""FastAPI application serving the provenance contract.

    QPROV_KEYS_FILE=keys.json QPROV_DB=provenance.sqlite QPROV_MODE=replay \
        python -m qmill_quantum_provenance.server

Request bodies are validated against the contract's own schemas; records are
the ones the in-process service assembles; every assembly is stored as a new
version. Provider credentials (live mode) come from the server environment.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..adapter import (
    ApplicationCompilationContext,
    ApplicationSoftwareContext,
    CreateProvenanceRecordRequest,
    SourceProgramInput,
)
from ..contract import load_contract
from ..models import canonical_job_id
from ..registry import ProvenanceAdapterRegistry
from ..service import ProvenanceService
from .auth import KeyRing, Principal
from .catalog import CaptureCatalog, CatalogIntegration
from .store import RecordStore

log = logging.getLogger(__name__)
_PROBLEM = "application/problem+json"
_VERSION_HEADER = "Provenance-Record-Version"


def problem(status: int, title: str, detail: str | None = None, **headers: str) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type=_PROBLEM, headers=headers or None)


def _adapter_classes() -> dict[str, Callable[[Any], Any]]:
    from ..adapters.braket import BraketProvenanceAdapter
    from ..adapters.ibm import IBMProvenanceAdapter
    from ..adapters.ionq import IonQProvenanceAdapter
    from ..adapters.quandela import QuandelaProvenanceAdapter

    return {
        "braket": BraketProvenanceAdapter,
        "ibm": IBMProvenanceAdapter,
        "ionq": IonQProvenanceAdapter,
        "quandela": QuandelaProvenanceAdapter,
    }


def _live_integration(provider: str):
    if provider == "braket":
        from ..live.braket import LiveBraketIntegration

        return LiveBraketIntegration()
    if provider == "ibm":
        from ..live.ibm import LiveIBMIntegration

        return LiveIBMIntegration()
    if provider == "ionq":
        from ..live.ionq import LiveIonQIntegration

        return LiveIonQIntegration()
    from ..live.quandela import LiveQuandelaIntegration

    return LiveQuandelaIntegration()


def registry_factory(mode: str, captures: Path | None) -> Callable[[], ProvenanceAdapterRegistry]:
    """A fresh registry per request: live retrieval layers hold per-job state."""

    classes = _adapter_classes()
    catalog = CaptureCatalog(captures) if mode == "replay" else None

    def build() -> ProvenanceAdapterRegistry:
        registry = ProvenanceAdapterRegistry()
        for provider, cls in classes.items():
            if catalog is not None:
                registry.register(
                    provider, lambda cls=cls, p=provider: cls(CatalogIntegration(p, catalog))
                )
            else:
                registry.register(provider, lambda cls=cls, p=provider: cls(_live_integration(p)))
        return registry

    return build


def _to_request(body: dict[str, Any], scope: str) -> CreateProvenanceRecordRequest:
    source = body.get("source_program")
    compilation = body.get("compilation_context")
    software = body.get("software_context")
    return CreateProvenanceRecordRequest(
        provider=body["provider"],
        external_job_id=body["external_job_id"],
        scope=scope,
        refresh=bool(body.get("refresh", False)),
        region=body.get("region"),
        source_program=SourceProgramInput(
            format=source["format"],
            reference=source.get("reference"),
            content_hash=(
                (source["content_hash"]["algorithm"], source["content_hash"]["value"])
                if source.get("content_hash")
                else None
            ),
        )
        if source
        else None,
        compilation_context=ApplicationCompilationContext(
            **{
                **compilation,
                "logical_to_physical_mapping": [
                    (entry["logical"], entry["physical"])
                    for entry in compilation["logical_to_physical_mapping"]
                ]
                if compilation.get("logical_to_physical_mapping") is not None
                else None,
            }
        )
        if compilation
        else None,
        software_context=ApplicationSoftwareContext(**software) if software else None,
        experiment_id=body.get("experiment_id"),
        requested_shots=body.get("requested_shots"),
    )


def create_app(
    store_path: str | Path,
    keyring: KeyRing,
    mode: str = "replay",
    captures: str | Path | None = "captures",
) -> FastAPI:
    contract = load_contract()
    resolver = jsonschema.RefResolver.from_schema(contract)
    schemas = contract["components"]["schemas"]
    request_validator = jsonschema.Draft202012Validator(
        schemas["CreateProvenanceRecordRequest"], resolver=resolver
    )
    record_validator = jsonschema.Draft202012Validator(
        schemas["ProvenanceRecord"], resolver=resolver
    )
    store = RecordStore(store_path)
    build_registry = registry_factory(mode, Path(captures) if captures else None)
    app = FastAPI(title=contract["info"]["title"], docs_url=None, redoc_url=None, openapi_url=None)

    def authenticate(request: Request, permission: str) -> Principal | JSONResponse:
        header = request.headers.get("authorization", "")
        scheme, _, key = header.partition(" ")
        principal = keyring.verify(key.strip()) if scheme.lower() == "bearer" and key else None
        if principal is None:
            return problem(
                401,
                "Unauthorized",
                "A valid API key is required.",
                **{"WWW-Authenticate": "Bearer"},
            )
        if permission not in principal.permissions:
            return problem(403, "Forbidden", f"The API key lacks {permission} permission.")
        return principal

    def record_response(stored, status: int) -> JSONResponse:
        return JSONResponse(
            stored.record, status_code=status, headers={_VERSION_HEADER: str(stored.version)}
        )

    def assemble(body: dict[str, Any], principal: Principal, refresh: bool) -> JSONResponse:
        request = _to_request({**body, "refresh": refresh}, principal.tenant)
        registry = build_registry()
        if not registry.is_registered(request.provider):
            return problem(404, "Not Found", "Provider not registered.")
        record, _ = ProvenanceService(registry=registry).create_record(request)
        payload = record.to_dict()
        errors = list(record_validator.iter_errors(payload))
        if errors:
            log.error("assembled record violates the contract: %s", errors[0].message)
            return problem(500, "Internal Server Error")
        version = store.add(principal.tenant, body, payload)
        return record_response(store.get(payload["record_id"], version), 201)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return problem(500, "Internal Server Error")

    @app.get("/v1/openapi.json", include_in_schema=False)
    async def published_contract() -> JSONResponse:
        return JSONResponse(contract)

    @app.post("/v1/provenance-records")
    async def create_record(request: Request) -> JSONResponse:
        principal = authenticate(request, "write")
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = json.loads(await request.body())
        except ValueError:
            return problem(400, "Bad Request", "Body is not valid JSON.")
        errors = sorted(request_validator.iter_errors(body), key=lambda e: list(e.path))
        if errors:
            where = "/".join(str(p) for p in errors[0].path) or "(body)"
            return problem(422, "Unprocessable Content", f"{where}: {errors[0].message}"[:300])
        if body.get("scope") not in (None, principal.tenant):
            return problem(403, "Forbidden", "The request names another tenant's scope.")
        record_id = canonical_job_id(body["provider"], body["external_job_id"], principal.tenant)
        existing = store.get(record_id)
        if existing is not None and existing.tenant == principal.tenant and not body.get("refresh"):
            return record_response(existing, 200)
        return assemble(body, principal, refresh=bool(body.get("refresh")))

    def owned(record_id: str, principal: Principal, version: int | None = None):
        stored = store.get(record_id, version)
        # Another tenant's record answers as missing: no existence leak.
        return stored if stored is not None and stored.tenant == principal.tenant else None

    @app.get("/v1/jobs/{job_id}/provenance")
    async def get_record(job_id: str, request: Request) -> JSONResponse:
        principal = authenticate(request, "read")
        if isinstance(principal, JSONResponse):
            return principal
        raw = request.query_params.get("version")
        version = None
        if raw is not None:
            if not raw.isdigit() or int(raw) < 1:
                return problem(400, "Bad Request", "version must be a positive integer.")
            version = int(raw)
        stored = owned(job_id, principal, version)
        if stored is None:
            return problem(404, "Not Found", "No such provenance record.")
        return record_response(stored, 200)

    @app.get("/v1/jobs/{job_id}/provenance/versions")
    async def list_versions(job_id: str, request: Request) -> JSONResponse:
        principal = authenticate(request, "read")
        if isinstance(principal, JSONResponse):
            return principal
        if owned(job_id, principal) is None:
            return problem(404, "Not Found", "No such provenance record.")
        return JSONResponse(
            {
                "record_id": job_id,
                "versions": [
                    {
                        "version": s.version,
                        "generated_at": s.generated_at,
                        "retrieved_at": s.retrieved_at,
                    }
                    for s in store.versions(job_id)
                ],
            }
        )

    @app.post("/v1/jobs/{job_id}/provenance/refresh")
    async def refresh_record(job_id: str, request: Request) -> JSONResponse:
        principal = authenticate(request, "write")
        if isinstance(principal, JSONResponse):
            return principal
        stored = owned(job_id, principal)
        if stored is None:
            return problem(404, "Not Found", "No such provenance record.")
        return assemble(stored.request, principal, refresh=True)

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    app = create_app(
        store_path=os.environ.get("QPROV_DB", "provenance.sqlite"),
        keyring=KeyRing.from_file(os.environ["QPROV_KEYS_FILE"]),
        mode=os.environ.get("QPROV_MODE", "replay"),
        captures=os.environ.get("QPROV_CAPTURES", "captures"),
    )
    uvicorn.run(
        app,
        host=os.environ.get("QPROV_HOST", "127.0.0.1"),
        port=int(os.environ.get("QPROV_PORT", "8000")),
    )
