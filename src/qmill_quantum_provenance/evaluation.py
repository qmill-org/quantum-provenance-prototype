"""Evaluation harness for the provenance prototype.

Produces a machine-readable report per provider:

- attribute counts grouped by evidence category (status),
- classification of every fixed inventory attribute (see
  ``attribute-inventory.json``) into exactly one provenance status per provider,
- QMill-facing logical operation count vs. adapter fixture-backed retrieval count,
- handwritten lines of code per adapter and for the shared, provider-independent
  provenance implementation (size only; not a measure of effort).

The basis is one real capture per provider path (``EVALUATION_CAPTURES``),
replayed with the application context from the run ledgers; no network or
credentials. The experiments are separate: baseline comparison
(``comparison``), failure injection (``experiments``) and live validation
(``live.validate``).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .adapter import (
    ApplicationCompilationContext,
    ApplicationSoftwareContext,
    CreateProvenanceRecordRequest,
    ProvenanceAdapter,
    SourceProgramInput,
)
from .adapters.braket import BraketProvenanceAdapter
from .adapters.ibm import IBMProvenanceAdapter
from .adapters.ionq import IonQProvenanceAdapter
from .adapters.quandela import QuandelaProvenanceAdapter
from .contract import validate_record
from .models import SCHEMA_VERSION
from .registry import ProvenanceAdapterRegistry
from .replay import ReplayIntegrationAdapter
from .service import ProvenanceService

# Report format identifier and version. Bump when the report shape changes.
_REPORT_FORMAT = "qmill.provenance.evaluation"
_REPORT_VERSION = "0.2.0"

# provider -> builder(replay_adapter) -> ProvenanceAdapter
_ADAPTER_BUILDERS: dict[str, Callable[[ReplayIntegrationAdapter], ProvenanceAdapter]] = {
    "braket": lambda replay: BraketProvenanceAdapter(replay),
    "ibm": lambda replay: IBMProvenanceAdapter(replay),
    "ionq": lambda replay: IonQProvenanceAdapter(replay),
    "quandela": lambda replay: QuandelaProvenanceAdapter(replay),
}

# provider -> adapter source file (for LOC accounting)
_ADAPTER_SOURCES: dict[str, str] = {
    "braket": "adapters/braket.py",
    "ibm": "adapters/ibm.py",
    "ionq": "adapters/ionq.py",
    "quandela": "adapters/quandela.py",
}

# shared, provider-independent provenance implementation modules
_SHARED_SOURCES = (
    "models.py",
    "adapter.py",
    "registry.py",
    "service.py",
    "redaction.py",
    "contract.py",
)

# Deterministic, representative application-captured context for the principal
# demonstration cases. These values are supplied by the (simulated) submitting
# application -- they are NOT read from the provider fixtures -- so the service
# records them as ``application_captured`` evidence.
# Evaluation basis: one real, purpose-run capture per provider path (v0.2.0).
# Records are built with the application context the run scripts recorded in
# the run ledgers, so application-captured evidence is real, not illustrative.
EVALUATION_CAPTURES: dict[str, str] = {
    "braket": "braket/c5f722a5-ee93-443e-8d89-f7ab285d7f69",  # IonQ Forte-1 via Braket
    "ibm": "ibm/dbvb21eppgvc73e5o380",  # Sampler, ibm_aachen
    "ionq": "ionq/01a1f2eb-d155-7632-bc4e-f340de096f01",  # forte-1 noise-model simulator
    "quandela": "quandela/5614c93a-8d77-43f0-81c6-7a13a935255e",  # sim:belenos HOM
}


def _ledger_entries() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted((_repo_root() / "runs").glob("ledger*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            job = entry.get("job_id") or str(entry.get("task_arn") or "").rsplit("/", 1)[-1]
            if job and entry.get("outcome", "created") == "created":
                entries[job] = entry
    return entries


def _job_key(external_job_id: str) -> str:
    return external_job_id.rsplit("/", 1)[-1]


def build_request(provider: str, fixture: dict[str, Any]) -> CreateProvenanceRecordRequest:
    """The evaluation request for a capture, with its recorded application context.

    Jobs without a run-ledger entry (e.g. the synthetic unit-test fixtures) are
    requested without application context.
    """

    external = str(fixture["external_job_id"])
    kwargs: dict[str, Any] = {
        "provider": provider,
        "external_job_id": external,
        "region": fixture.get("region"),
    }
    entry = _ledger_entries().get(_job_key(external))
    if entry is None:
        return CreateProvenanceRecordRequest(**kwargs)
    context = entry.get("application_context") or {}
    source = context.get("source_program")
    if source:
        kwargs["source_program"] = SourceProgramInput(
            format="openqasm3",
            reference=source.get("reference"),
            content_hash=("sha256", source["sha256"]) if source.get("sha256") else None,
        )
    compilation = context.get("compilation")
    if compilation:
        layout = compilation.get("final_layout") or []
        kwargs["compilation_context"] = ApplicationCompilationContext(
            compiler_name=compilation.get("compiler"),
            compiler_version=compilation.get("compiler_version"),
            optimization_level=compilation.get("optimization_level"),
            random_seed=compilation.get("seed_transpiler"),
            logical_to_physical_mapping=[(i, q) for i, q in enumerate(layout)] or None,
        )
    software = dict(context.get("software") or {})
    if software:
        client = next(
            (
                name
                for name in ("qiskit-ibm-runtime", "boto3", "httpx", "perceval-quandela")
                if name in software
            ),
            None,
        )
        kwargs["software_context"] = ApplicationSoftwareContext(
            provider_client=client,
            provider_client_version=software.get(client) if client else None,
            compiler_name="qiskit" if compilation and "qiskit" in software else None,
            compiler_version=software.get("qiskit") if compilation else None,
            python_version=software.get("python"),
            framework_versions={
                k: str(v)
                for k, v in software.items()
                if k not in ("python", client) and v is not None
            }
            or None,
        )
    shots = entry.get("max_samples") if provider == "quandela" else entry.get("shots")
    if isinstance(shots, int):
        kwargs["requested_shots"] = shots
    return CreateProvenanceRecordRequest(**kwargs)


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    # .../src/qmill_quantum_provenance/evaluation.py
    return Path(__file__).resolve().parents[2]


def _examples_dir() -> Path:
    return _repo_root() / "artifact" / "examples"


def _provenance_docs_dir() -> Path:
    return _repo_root() / "artifact"


def _inventory_path() -> Path:
    return _provenance_docs_dir() / "attribute-inventory.json"


def load_inventory() -> dict[str, Any]:
    """Load the versioned, machine-readable provenance attribute inventory."""

    with _inventory_path().open(encoding="utf-8") as stream:
        return json.load(stream)


def _resolve_pointer(payload: Any, pointer: str) -> tuple[bool, Any]:
    """Resolve a JSON Pointer. Returns ``(found, value)``."""

    if pointer in ("", "/"):
        return True, payload
    current = payload
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return False, None
            if 0 <= index < len(current):
                current = current[index]
            else:
                return False, None
        else:
            return False, None
    return True, current


def _is_applicable(rule: Any, provider: str) -> bool:
    if rule == "all" or rule is None:
        return True
    if isinstance(rule, dict):
        if "not_applicable" in rule:
            return provider not in rule["not_applicable"]
        if "applicable_only" in rule:
            return provider in rule["applicable_only"]
    return True


def _classify_artifact_role(
    locator: dict[str, Any], payload: dict[str, Any], evidence_by_path: dict[str, str]
) -> str:
    role = locator.get("role")
    for index, artifact in enumerate(payload.get("artifacts") or []):
        if artifact.get("role") == role:
            path = f"/artifacts/{index}"
            return evidence_by_path.get(path, "unclassified")
    for item in payload.get("evidence") or []:
        if item.get("path") == "/artifacts" and item.get("artifact_role") == role:
            return item["status"]
    return "unavailable"


def _classify_attribute(
    attr: dict[str, Any],
    provider: str,
    payload: dict[str, Any],
    evidence_by_path: dict[str, str],
) -> str:
    if not _is_applicable(attr.get("applicability", "all"), provider):
        return "not_applicable"
    locator = attr.get("locator")
    if isinstance(locator, dict) and locator.get("type") == "artifact_role":
        return _classify_artifact_role(locator, payload, evidence_by_path)
    evidence_pointer = attr["evidence_pointer"]
    if evidence_pointer in evidence_by_path:
        return evidence_by_path[evidence_pointer]
    found, value = _resolve_pointer(payload, attr["value_pointer"])
    if found and value is not None:
        # Emitted but unqualified: this is a gap the evaluation must surface.
        return "unclassified"
    # Absent-but-applicable: honestly reported as unavailable (distinct from
    # not_applicable, which means the attribute does not apply to this provider).
    return "unavailable"


def classify_inventory(
    payload: dict[str, Any], inventory: dict[str, Any], provider: str
) -> dict[str, str]:
    """Classify every inventory attribute for a single provider record.

    Every attribute receives exactly one status. Applicable attributes that are
    emitted in the record but carry no evidence are returned as ``unclassified``
    so the evaluation test can fail rather than silently omit them.
    """

    evidence_by_path: dict[str, str] = {}
    for item in payload.get("evidence", []):
        evidence_by_path.setdefault(item["path"], item["status"])
    return {
        attr["id"]: _classify_attribute(attr, provider, payload, evidence_by_path)
        for attr in inventory["attributes"]
    }


def count_loc(path: Path) -> int:
    """Count non-blank, non-comment physical lines."""

    total = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        total += 1
    return total


def build_service(fixtures: dict[str, dict[str, Any]]) -> ProvenanceService:
    """Service whose adapters replay the supplied fixtures (no network)."""

    registry = ProvenanceAdapterRegistry()
    for provider, fixture in fixtures.items():
        if provider not in _ADAPTER_BUILDERS:
            raise KeyError(f"No adapter builder registered for provider {provider!r}")
        builder = _ADAPTER_BUILDERS[provider]
        registry.register(
            provider,
            lambda builder=builder, fixture=fixture: builder(ReplayIntegrationAdapter(fixture)),
        )
    return ProvenanceService(registry=registry)


def _load_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def evaluate(fixture_paths: dict[str, Path]) -> dict[str, Any]:
    fixtures = {provider: _load_fixture(path) for provider, path in fixture_paths.items()}
    inventory = load_inventory()
    service = build_service(fixtures)

    providers_report: dict[str, Any] = {}
    for provider, fixture in fixtures.items():
        request = build_request(provider, fixture)
        record, _created = service.create_record(request)
        payload = record.to_dict()
        validate_record(payload)

        evidence_by_status = Counter(item["status"] for item in payload["evidence"])
        op_by_actor: Counter[str] = Counter()
        for op in payload["operations"]:
            op_by_actor[op["actor"]] += int(op.get("count", 1))

        classifications = classify_inventory(payload, inventory, provider)
        classification_counts = Counter(classifications.values())

        adapter_source = _package_dir() / _ADAPTER_SOURCES[provider]
        providers_report[provider] = {
            "record_id": payload["record_id"],
            "fixture_id": str(fixture["external_job_id"]),
            "attribute_evidence_counts": dict(sorted(evidence_by_status.items())),
            "evidence_total": sum(evidence_by_status.values()),
            "inventory_classification": {
                "counts": dict(sorted(classification_counts.items())),
                "by_attribute": dict(sorted(classifications.items())),
                "unclassified": classification_counts.get("unclassified", 0),
            },
            "operations": {
                "qmill_facing": op_by_actor.get("qmill", 0),
                "adapter_upstream": op_by_actor.get("adapter", 0),
                "provider_reported": op_by_actor.get("provider", 0),
            },
            "adapter_loc": count_loc(adapter_source),
            "results_available": payload["results"]["available"],
        }

    shared_loc = {name: count_loc(_package_dir() / name) for name in _SHARED_SOURCES}
    return {
        "report_format": _REPORT_FORMAT,
        "report_version": _REPORT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "attribute_inventory_version": inventory["inventory_version"],
        "providers": providers_report,
        "shared_provider_independent_implementation_loc": shared_loc,
        "shared_provider_independent_implementation_loc_total": sum(shared_loc.values()),
        "experiments": {
            "baseline_comparison": "artifact/baseline-comparison.json",
            "failure_injection": "artifact/failure-injection.json",
            "live_validation": "captures/validation-v0.2.0-adapters.json",
        },
    }


def _default_fixture_paths() -> dict[str, Path]:
    captures = _repo_root() / "captures"
    return {
        provider: captures / relative / "fixture.json"
        for provider, relative in EVALUATION_CAPTURES.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provenance prototype evaluation")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the JSON report to this path (default: stdout).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Verify the committed evaluation-results.json matches a freshly "
            "generated report; exit non-zero on drift."
        ),
    )
    args = parser.parse_args(argv)

    report = evaluate(_default_fixture_paths())
    text = json.dumps(report, indent=2, sort_keys=True)

    if args.check:
        committed_path = _provenance_docs_dir() / "evaluation-results.json"
        if not committed_path.exists():
            print(f"Missing committed report: {committed_path}")
            return 1
        committed = committed_path.read_text(encoding="utf-8")
        if committed != text + "\n":
            print(
                "Committed evaluation-results.json is stale. Regenerate with "
                "`python -m qmill_quantum_provenance.evaluation "
                f"--output {committed_path}`."
            )
            return 1
        print("evaluation-results.json is up to date.")
        return 0

    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "build_request",
    "build_service",
    "classify_inventory",
    "count_loc",
    "evaluate",
    "load_inventory",
    "main",
]
