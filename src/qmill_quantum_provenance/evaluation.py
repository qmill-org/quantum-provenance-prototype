"""Evaluation harness for the provenance prototype.

Produces a machine-readable report per provider:

- attribute counts grouped by evidence category (status),
- classification of every fixed inventory attribute (see
  ``attribute-inventory.json``) into exactly one provenance status per provider,
- QMill-facing logical operation count vs. adapter fixture-backed retrieval count,
- handwritten lines of code per adapter and for the shared, provider-independent
  provenance implementation,
- runnable schema-change, provider-input, and partial-record experiments whose
  backward-compatibility and isolation claims are measured empirically.

Runs entirely off sanitized fixtures (no network, no credentials).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
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
from .contract import load_contract, validate_record
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
}

# provider -> adapter source file (for LOC accounting)
_ADAPTER_SOURCES: dict[str, str] = {
    "braket": "adapters/braket.py",
    "ibm": "adapters/ibm.py",
    "ionq": "adapters/ionq.py",
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
_APP_SOURCE_PROGRAMS: dict[str, str] = {
    "braket": ("OPENQASM 3.0;\nqubit[2] q;\nbit[2] c;\nh q[0];\ncx q[0], q[1];\nc = measure q;\n"),
    "ibm": ("OPENQASM 3.0;\nqubit[5] q;\nbit[5] c;\nh q[0];\ncx q[0], q[1];\nc = measure q;\n"),
}

_APP_COMPILATION: dict[str, ApplicationCompilationContext] = {
    "braket": ApplicationCompilationContext(
        compiler_name="qiskit-transpiler",
        compiler_version="2.5.0",
        optimization_level=2,
        logical_to_physical_mapping=[(0, 0), (1, 1)],
    ),
    "ibm": ApplicationCompilationContext(
        compiler_name="qiskit-transpiler",
        compiler_version="2.5.0",
        optimization_level=3,
        logical_to_physical_mapping=[(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)],
    ),
}

_APP_SOFTWARE: dict[str, ApplicationSoftwareContext] = {
    "braket": ApplicationSoftwareContext(
        provider_client="amazon-braket-sdk",
        provider_client_version="1.97.0",
        compiler_name="qiskit-transpiler",
        compiler_version="2.5.0",
        python_version="3.12",
        framework_versions={"qiskit": "2.5.0", "qiskit-braket-provider": "0.7.0"},
    ),
    "ibm": ApplicationSoftwareContext(
        provider_client="qiskit-ibm-runtime",
        provider_client_version="0.43.0",
        compiler_name="qiskit-transpiler",
        compiler_version="2.5.0",
        python_version="3.12",
        framework_versions={"qiskit": "2.5.0", "qiskit-ibm-runtime": "0.43.0"},
    ),
}


def _app_source_program(provider: str) -> SourceProgramInput:
    program = _APP_SOURCE_PROGRAMS[provider]
    digest = hashlib.sha256(program.encode("utf-8")).hexdigest()
    return SourceProgramInput(
        format="openqasm3",
        reference=f"app://demo/{provider}/bell",
        content_hash=("sha256", digest),
    )


def build_request(provider: str, fixture: dict[str, Any]) -> CreateProvenanceRecordRequest:
    """Build the canonical evaluation request for a provider fixture.

    Braket and IBM are the principal demonstration cases and carry deterministic
    application-captured context (source program hash, compiler/transpiler,
    optimization level, logical-to-physical mapping, provider-client version, and
    Python/framework versions). IonQ is exercised without application context.
    """

    kwargs: dict[str, Any] = {
        "provider": provider,
        "external_job_id": str(fixture["external_job_id"]),
        "region": fixture.get("region"),
    }
    if provider in _APP_COMPILATION:
        kwargs["source_program"] = _app_source_program(provider)
        kwargs["compilation_context"] = _APP_COMPILATION[provider]
        kwargs["software_context"] = _APP_SOFTWARE[provider]
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
        "schema_change_experiment": run_schema_change_experiment(),
        "provider_input_experiment": run_provider_input_experiment(fixture_paths),
        "partial_record_experiment": run_partial_record_experiment(),
    }


# A representative additive schema change: a new OPTIONAL top-level attribute.
# Kept out of the ``required`` list so existing records remain valid, and the
# canonical schema uses ``additionalProperties: false`` so a record carrying the
# attribute is genuinely rejected until the schema is extended.
_SCHEMA_CHANGE_ATTRIBUTE = "cost"
_SCHEMA_CHANGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["currency", "amount"],
    "properties": {
        "currency": {"type": "string"},
        "amount": {"type": "number"},
    },
    "additionalProperties": False,
}


def _extended_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of the contract with the additive attribute added."""

    extended = copy.deepcopy(contract)
    schemas = extended["components"]["schemas"]
    schemas["Cost"] = copy.deepcopy(_SCHEMA_CHANGE_SCHEMA)
    record = schemas["ProvenanceRecord"]
    # Additive: new optional property, deliberately NOT added to ``required``.
    record["properties"][_SCHEMA_CHANGE_ATTRIBUTE] = {"$ref": "#/components/schemas/Cost"}
    return extended


def _validates(record: dict[str, Any], contract: dict[str, Any]) -> bool:
    import jsonschema

    resolver = jsonschema.RefResolver.from_schema(contract)
    validator = jsonschema.Draft202012Validator(
        contract["components"]["schemas"]["ProvenanceRecord"], resolver=resolver
    )
    try:
        validator.validate(record)
    except jsonschema.ValidationError:
        return False
    return True


def run_schema_change_experiment(example_dir: Path | None = None) -> dict[str, Any]:
    """Characterize the cost and isolation of an additive schema change.

    The backward-compatibility and necessity claims are *measured* against the
    canonical contract: every existing example record must still validate after
    the change, and a record carrying the new attribute must be rejected by the
    original contract yet accepted by the extended one. The touch-set (files a
    production implementation must modify) is reported as an architectural
    analysis, split into the one-time shared-implementation change, the per-provider
    adapter change, and the seam infrastructure that stays untouched.
    """

    contract = load_contract()
    extended = _extended_contract(contract)

    example_dir = example_dir or _examples_dir()
    examples = sorted(example_dir.glob("*.json"))

    per_example = []
    for path in examples:
        record = json.loads(path.read_text(encoding="utf-8"))
        per_example.append(
            {
                "example": path.name,
                "valid_original": _validates(record, contract),
                "valid_extended": _validates(record, extended),
            }
        )
    backward_compatible = bool(examples) and all(
        item["valid_original"] and item["valid_extended"] for item in per_example
    )

    # A record carrying the new attribute proves the change is necessary: it is
    # rejected by the original contract (additionalProperties: false) and only
    # accepted once the schema is extended.
    probe = json.loads(examples[0].read_text(encoding="utf-8")) if examples else {}
    probe = dict(probe)
    probe[_SCHEMA_CHANGE_ATTRIBUTE] = {"currency": "USD", "amount": 12.5}
    rejected_by_original = not _validates(probe, contract)
    accepted_by_extended = _validates(probe, extended)

    return {
        "change": {
            "type": "additive_optional_attribute",
            "attribute": _SCHEMA_CHANGE_ATTRIBUTE,
            "location": f"/{_SCHEMA_CHANGE_ATTRIBUTE}",
        },
        "measured": {
            "examples_checked": len(examples),
            "backward_compatible": backward_compatible,
            "new_attribute_rejected_by_original": rejected_by_original,
            "new_attribute_accepted_by_extended": accepted_by_extended,
            "change_is_necessary": rejected_by_original and accepted_by_extended,
            "per_example": per_example,
        },
        "touch_set": {
            "shared_implementation": [
                "src/qmill_quantum_provenance/openapi.json",
                "src/qmill_quantum_provenance/models.py",
                "src/qmill_quantum_provenance/adapter.py",
                "src/qmill_quantum_provenance/service.py",
            ],
            "shared_implementation_files": 4,
            "per_provider_adapter": {
                "rule": (
                    "one localized change per provider that can source the "
                    "attribute (0..N); adapters that cannot source it are "
                    "unchanged."
                ),
            },
            "unchanged_infrastructure": [
                "src/qmill_quantum_provenance/registry.py",
                "src/qmill_quantum_provenance/replay.py",
                "src/qmill_quantum_provenance/contract.py",
                "src/qmill_quantum_provenance/evaluation.py",
            ],
        },
    }


def _stable_record(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop wall-clock fields so two runs of the same fixture compare equal."""

    stable = copy.deepcopy(payload)
    stable.pop("generated_at", None)
    stable.pop("retrieved_at", None)
    return stable


def _evidence_status(payload: dict[str, Any], path: str) -> str | None:
    for item in payload["evidence"]:
        if item.get("path") == path:
            return item.get("status")
    return None


# The IBM adapter sources /device/qubit_count from this upstream field. Renaming
# it simulates a provider-side input change that the current mapping no longer
# recognizes.
_RENAMED_IBM_FIELD = ("device", "provider_properties", "num_qubits")
_RENAMED_IBM_FIELD_TO = "qubit_total"


def _rename_ibm_field(fixture: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the IBM fixture with the qubit-count field renamed."""

    mutated = copy.deepcopy(fixture)
    container: Any = mutated
    *parents, leaf = _RENAMED_IBM_FIELD
    for key in parents:
        container = container.get(key) if isinstance(container, dict) else None
        if container is None:
            return mutated
    if isinstance(container, dict) and leaf in container:
        container[_RENAMED_IBM_FIELD_TO] = container.pop(leaf)
    return mutated


def run_provider_input_experiment(
    fixture_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Characterize the isolation of a provider-side *input* change.

    Unlike the schema-change experiment (which alters the shared contract), this
    renames an upstream field that only the IBM adapter reads. It empirically
    shows that:

    - the IBM record still validates against the unchanged contract (the mapping
      degrades gracefully rather than crashing),
    - the affected attribute (``/device/qubit_count``) degrades to
      ``unavailable`` instead of emitting a wrong value,
    - the Braket and IonQ records are byte-for-byte unchanged, and
    - the fix is confined to a single provider adapter file.
    """

    paths = fixture_paths or _default_fixture_paths()
    fixtures = {provider: _load_fixture(path) for provider, path in paths.items()}

    # Baseline: every adapter reads its pristine fixture.
    baseline_service = build_service(fixtures)
    baseline: dict[str, dict[str, Any]] = {}
    for provider, fixture in fixtures.items():
        request = build_request(provider, fixture)
        record, _ = baseline_service.create_record(request)
        baseline[provider] = record.to_dict()

    # Perturbed: only the IBM fixture's upstream field is renamed.
    mutated_fixtures = dict(fixtures)
    mutated_fixtures["ibm"] = _rename_ibm_field(fixtures["ibm"])
    mutated_service = build_service(mutated_fixtures)
    mutated: dict[str, dict[str, Any]] = {}
    for provider, fixture in mutated_fixtures.items():
        request = build_request(provider, fixture)
        record, _ = mutated_service.create_record(request)
        mutated[provider] = record.to_dict()

    ibm_before = baseline["ibm"]
    ibm_after = mutated["ibm"]

    ibm_still_validates = _validates(ibm_after, load_contract())
    qubit_count_before = ibm_before["device"].get("qubit_count")
    qubit_count_after = ibm_after["device"].get("qubit_count")
    degraded_status = _evidence_status(ibm_after, "/device/qubit_count")

    unaffected = {
        provider: _stable_record(baseline[provider]) == _stable_record(mutated[provider])
        for provider in ("braket", "ionq")
        if provider in baseline and provider in mutated
    }

    return {
        "change": {
            "type": "provider_input_field_rename",
            "provider": "ibm",
            "renamed_field": ".".join(_RENAMED_IBM_FIELD),
            "renamed_to": _RENAMED_IBM_FIELD_TO,
            "affected_attribute": "/device/qubit_count",
        },
        "measured": {
            "ibm_record_still_validates": ibm_still_validates,
            "qubit_count_before": qubit_count_before,
            "qubit_count_after": qubit_count_after,
            "affected_attribute_degraded_to_unavailable": (
                qubit_count_after is None and degraded_status == "unavailable"
            ),
            "affected_attribute_status_after": degraded_status,
            "other_providers_unchanged": unaffected,
            "isolation_holds": (
                ibm_still_validates
                and qubit_count_after is None
                and degraded_status == "unavailable"
                and all(unaffected.values())
            ),
        },
        "touch_set": {
            "to_restore_attribute": ["src/qmill_quantum_provenance/adapters/ibm.py"],
            "files": 1,
            "rule": (
                "a provider-side input change is repaired in exactly one adapter "
                "file; the contract, shared implementation, and other adapters are "
                "untouched."
            ),
        },
    }


def _default_fixture_paths() -> dict[str, Path]:
    root = _repo_root()
    fixtures = root / "tests" / "fixtures"
    return {
        "braket": fixtures / "braket" / "completed.json",
        "ibm": fixtures / "ibm" / "completed.json",
        "ionq": fixtures / "ionq" / "completed.json",
    }


def _partial_fixture_paths() -> dict[str, Path]:
    root = _repo_root()
    fixtures = root / "tests" / "fixtures"
    return {
        "braket": fixtures / "braket" / "completed_no_calibration.json",
        "ibm": fixtures / "ibm" / "completed_no_calibration.json",
        "ionq": fixtures / "ionq" / "completed_no_calibration.json",
    }


def run_partial_record_experiment(
    fixture_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Characterize graceful degradation for partial provider records.

    Each provider is replayed from a fixture that omits calibration data. The
    experiment empirically shows that, with an attribute genuinely missing
    upstream, every record still validates against the unchanged contract, the
    device characterization degrades to ``unavailable`` (rather than being
    fabricated), and no applicable emitted attribute is left ``unclassified``.
    """

    paths = fixture_paths or _partial_fixture_paths()
    fixtures = {provider: _load_fixture(path) for provider, path in paths.items()}
    inventory = load_inventory()
    service = build_service(fixtures)

    per_provider: dict[str, Any] = {}
    for provider, fixture in fixtures.items():
        request = build_request(provider, fixture)
        record, _ = service.create_record(request)
        payload = record.to_dict()
        validates = _validates(payload, load_contract())
        characterization_status = _evidence_status(payload, "/characterization")
        classifications = classify_inventory(payload, inventory, provider)
        counts = Counter(classifications.values())
        per_provider[provider] = {
            "record_validates": validates,
            "characterization_status": characterization_status,
            "characterization_unavailable": characterization_status == "unavailable",
            "unclassified": counts.get("unclassified", 0),
            "unavailable_attributes": counts.get("unavailable", 0),
        }

    return {
        "change": {
            "type": "partial_provider_record",
            "omitted": "device_calibration_data",
            "affected_attribute": "/characterization",
        },
        "measured": {
            "per_provider": per_provider,
            "all_records_validate": all(item["record_validates"] for item in per_provider.values()),
            "characterization_degrades_everywhere": all(
                item["characterization_unavailable"] for item in per_provider.values()
            ),
            "no_unclassified_attributes": all(
                item["unclassified"] == 0 for item in per_provider.values()
            ),
        },
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
    "run_partial_record_experiment",
    "run_provider_input_experiment",
    "run_schema_change_experiment",
]
