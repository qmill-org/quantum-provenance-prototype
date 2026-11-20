"""Stage B: faults at the integration seam, through adapters and service.

Each fault is a mutation of a real capture's fixture, so arms V1 (``v0.1.0``,
run from a worktree) and V2 (current) receive identical inputs. Measures M1-M7
follow protocols/failure-injection.md.
"""

from __future__ import annotations

import copy
import itertools
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..adapter import CreateProvenanceRecordRequest
from ..comparison.run import tagged_records
from ..evaluation import _resolve_pointer, build_service, classify_inventory

BASES = {
    "braket-rigetti": "braket/8110d507-c11a-4473-88e0-0dfa04c468ec",
    "braket-ionq": "braket/c5f722a5-ee93-443e-8d89-f7ab285d7f69",
    "braket-quera": "braket/808c58a0-b1d5-4165-9a9b-1fd85258677e",
    "ibm-sampler": "ibm/dbvb21eppgvc73e5o380",
    "ionq-sim": "ionq/01a1f2eb-d155-7632-bc4e-f340de096f01",
    "quandela-sim": "quandela/5614c93a-8d77-43f0-81c6-7a13a935255e",
}
ERRORS = ("JobNotFoundError", "AccessDeniedError", "ThrottledError", "ProviderIntegrationError")
OPERATIONS = ("get_status", "get_result", "get_device_details")
EXPECTED_REASON = {
    "JobNotFoundError": "not_found_by_provider",
    "AccessDeniedError": "authentication_scope_insufficient",
    "ThrottledError": "upstream_request_failed",
    "ProviderIntegrationError": "upstream_request_failed",
}
SECTIONS = (
    "characterization",
    "device_properties",
    "result_payload",
    "compiled",
    "counts",
    "timestamps",
    "shots",
    "metadata",
)
MALFORMED = (
    "shots_string",
    "time_unparsable",
    "count_non_integer",
    "metric_non_numeric",
    "timestamps_not_object",
    "payload_list",
)
_TIME_KEYS = (
    "timestamps",
    "creation_datetime",
    "start_time",
    "createdAt",
    "endedAt",
    "submitted_at",
    "completed_at",
)
_VALUE_STATES = {"provider_supplied", "provider_passthrough", "aggregator_normalized", "derived"}

RESULTS = "results.*"
DURATIONS = "execution.*_duration_ms"
AFFECTED: dict[str, tuple[str, ...]] = {
    "get_status": ("*",),
    "get_device_details": ("device.qubit_count", "device.type", "characterization"),
    "get_result": (RESULTS, "artifact.compiled", "execution.executed_shots"),
    "characterization": ("device.qubit_count", "characterization"),
    "device_properties": ("device.qubit_count",),
    "result_payload": (RESULTS, "artifact.compiled", "execution.executed_shots"),
    "compiled": ("artifact.compiled",),
    "counts": (RESULTS,),
    "timestamps": ("job.created_at", "job.ended_at", DURATIONS),
    "shots": ("job.shots",),
    "metadata": (),
    "shots_string": ("job.shots",),
    "time_unparsable": ("job.created_at", "job.ended_at", DURATIONS),
    "count_non_integer": (RESULTS,),
    "metric_non_numeric": ("characterization",),
    "timestamps_not_object": ("job.created_at", "job.ended_at", DURATIONS),
    "payload_list": (RESULTS, "artifact.compiled", "execution.executed_shots"),
}


# -- mutations ------------------------------------------------------------------


def _remove(fixture: dict[str, Any], section: str) -> None:
    snapshot = fixture.setdefault("snapshot", {})
    metadata = snapshot.setdefault("metadata", {})
    result = fixture.get("result") or {}
    device = fixture.get("device") or {}
    if section == "characterization":
        device["calibration"] = None
    elif section == "device_properties":
        device["provider_properties"] = None
    elif section == "result_payload":
        result["raw_payload"] = None
    elif section == "compiled":
        result["compiled_circuit"] = None
    elif section == "counts":
        result["measurement_counts"] = {}
        payload = result.get("raw_payload")
        if isinstance(payload, dict):
            for key in ("measurements", "measurementProbabilities", "histogram"):
                payload.pop(key, None)
    elif section == "timestamps":
        snapshot["created_at"] = snapshot["ended_at"] = None
        for key in _TIME_KEYS:
            metadata.pop(key, None)
    elif section == "shots":
        snapshot["shots"] = None
        metadata.pop("shots", None)
    elif section == "metadata":
        snapshot["metadata"] = {}


def _malform(fixture: dict[str, Any], case: str) -> bool:
    """Apply a malformed value; False when the base has nothing to malform."""

    snapshot = fixture.get("snapshot") or {}
    metadata = snapshot.get("metadata") or {}
    result = fixture.get("result") or {}
    device = fixture.get("device") or {}
    if case == "shots_string":
        if snapshot.get("shots") is None:
            return False
        snapshot["shots"] = str(snapshot["shots"])
    elif case == "time_unparsable":
        # Snapshot times are parsed by the seam; malform the provider field the
        # adapter parses itself.
        stamps = metadata.get("timestamps")
        if isinstance(stamps, dict) and "created" in stamps:
            stamps["created"] = "not-a-date"
        elif "creation_datetime" in metadata:
            metadata["creation_datetime"] = "not-a-date"
        else:
            return False
    elif case == "count_non_integer":
        counts = result.get("measurement_counts") or {}
        histogram = (result.get("raw_payload") or {}).get("histogram")
        if counts:
            key = next(iter(counts))
            counts[key] = str(counts[key])
        elif isinstance(histogram, dict) and histogram:
            key = next(iter(histogram))
            histogram[key] = f"{histogram[key]}x"
        else:
            return False
    elif case == "metric_non_numeric":
        metrics = (device.get("calibration") or {}).get("metrics")
        if not metrics:
            return False
        metrics[next(iter(metrics))] = "abc"
    elif case == "timestamps_not_object":
        if "timestamps" not in metadata:
            return False
        metadata["timestamps"] = "2026-11-19T08:19:17Z"
    elif case == "payload_list":
        if not isinstance(result.get("raw_payload"), dict):
            return False
        result["raw_payload"] = []
    return True


def cases() -> list[tuple[str, str, Any]]:
    """(family, name, mutation spec)."""

    out: list[tuple[str, str, Any]] = []
    for error in ERRORS:
        for operation in OPERATIONS:
            out.append(("upstream_error", f"{error}@{operation}", (error, operation)))
    for size in (1, 2, len(SECTIONS)):
        for combo in itertools.combinations(SECTIONS, size):
            out.append(("missing_sections", "+".join(combo), combo))
    for case in MALFORMED:
        out.append(("malformed", case, case))
    return out


def mutate(base: dict[str, Any], family: str, spec: Any) -> dict[str, Any] | None:
    fixture = copy.deepcopy(base)
    if family == "upstream_error":
        error, operation = spec
        fixture["upstream_errors"] = {operation: {"error": error, "message": f"injected {error}"}}
    elif family == "missing_sections":
        for section in spec:
            _remove(fixture, section)
    elif not _malform(fixture, spec):
        return None
    return fixture


def affected_patterns(family: str, spec: Any) -> tuple[str, ...]:
    if family == "upstream_error":
        return AFFECTED[spec[1]]
    if family == "missing_sections":
        return tuple(p for section in spec for p in AFFECTED[section])
    return AFFECTED[spec]


def _matches(attribute: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern == "*" or pattern == attribute:
            return True
        if pattern == RESULTS and attribute.startswith("results."):
            return True
        if (
            pattern == DURATIONS
            and attribute.startswith("execution.")
            and attribute.endswith("_duration_ms")
        ):
            return True
    return False


# -- arms -----------------------------------------------------------------------


def _v2_record(fixture: dict[str, Any]) -> dict[str, Any] | None:
    try:
        record, _ = build_service({fixture["provider"]: fixture}).create_record(
            CreateProvenanceRecordRequest(
                provider=fixture["provider"],
                external_job_id=fixture["external_job_id"],
                region=fixture.get("region"),
            )
        )
    except Exception:  # noqa: BLE001 - a crash is a measured outcome
        return None
    return record.to_dict()


def _git_json(revision: str, path: str) -> dict[str, Any]:
    text = subprocess.run(
        ["git", "show", f"{revision}:{path}"], check=True, capture_output=True, text=True
    ).stdout
    return json.loads(text)


def _validator(contract: dict[str, Any]):
    import jsonschema

    resolver = jsonschema.RefResolver.from_schema(contract)
    schema = contract["components"]["schemas"]["ProvenanceRecord"]
    return jsonschema.Draft202012Validator(schema, resolver=resolver)


# -- measures -------------------------------------------------------------------


def _inherited_reason(evidence: dict[str, dict[str, Any]], pointer: str) -> str | None:
    """Reason at the attribute's evidence path or its nearest ancestor."""

    path = pointer
    while path:
        reason = (evidence.get(path) or {}).get("reason")
        if reason:
            return reason
        path = path.rsplit("/", 1)[0]
    return None


def _attribute_view(
    record: dict[str, Any], inventory: dict[str, Any], provider: str
) -> dict[str, tuple[str, Any, str | None]]:
    classes = classify_inventory(record, inventory, provider)
    evidence = {item["path"]: item for item in record.get("evidence") or []}
    view = {}
    for attribute in inventory["attributes"]:
        ident = attribute["id"]
        locator = attribute.get("locator")
        if isinstance(locator, dict) and locator.get("type") == "artifact_role":
            value = next(
                (
                    a.get("content_hash") or a.get("reference") or True
                    for a in record.get("artifacts") or []
                    if a.get("role") == locator.get("role")
                ),
                None,
            )
            reason = next(
                (
                    e.get("reason")
                    for e in record.get("evidence") or []
                    if e.get("path") == "/artifacts"
                    and e.get("artifact_role") == locator.get("role")
                ),
                None,
            )
        else:
            value = _resolve_pointer(record, attribute["value_pointer"])[1]
            reason = _inherited_reason(evidence, attribute["evidence_pointer"])
        view[ident] = (classes[ident], value, reason)
    return view


def measure(
    record: dict[str, Any] | None,
    base: dict[str, Any] | None,
    inventory: dict[str, Any],
    validator,
    provider: str,
    family: str,
    spec: Any,
) -> dict[str, Any]:
    if record is None:
        return {"M1_crash": True, "M2_record": False}
    out: dict[str, Any] = {"M1_crash": False, "M2_record": True}
    errors = sorted(validator.iter_errors(record), key=str)
    out["M3_valid"] = not errors
    if errors:
        out["schema_error"] = errors[0].message[:160]
    new_codes = sorted(
        {w["code"] for w in record.get("warnings") or []}
        - {w["code"] for w in (base or {}).get("warnings") or []}
    )
    out["M7_signal"] = bool(new_codes)
    out["new_warnings"] = new_codes
    if (family == "missing_sections" and "metadata" in spec) or base is None:
        return out  # protocol: missing-metadata cases are reported for M1-M3 and M7 only
    patterns = affected_patterns(family, spec)
    view = _attribute_view(record, inventory, provider)
    base_view = _attribute_view(base, inventory, provider)
    fabricated, wrong_reason, leaked, dependent = [], [], [], []
    for ident, (status, value, reason) in view.items():
        base_status, base_value, _ = base_view[ident]
        if _matches(ident, patterns):
            if status in _VALUE_STATES and value != base_value:
                fabricated.append(f"{ident}={status}")
            if family == "upstream_error" and status == "unavailable":
                expected = EXPECTED_REASON[spec[0]]
                if reason != expected:
                    wrong_reason.append(f"{ident}:{reason}")
        elif status != base_status:
            # A derived attribute legitimately changes when its source is removed.
            if base_status == "derived":
                dependent.append(f"{ident}:{base_status}->{status}")
                if status in _VALUE_STATES and value != base_value:
                    fabricated.append(f"{ident}={status}")
            else:
                leaked.append(f"{ident}:{base_status}->{status}")
    out["M4_honest"] = not fabricated
    out["M6_isolated"] = not leaked
    if dependent:
        out["dependent_derived"] = dependent
    if fabricated:
        out["fabricated"] = fabricated
    if leaked:
        out["leaked"] = leaked
    if family == "upstream_error":
        out["M5_reason"] = not wrong_reason
        if wrong_reason:
            out["wrong_reason"] = wrong_reason
    return out


def run_stage_b(captures: Path) -> list[dict[str, Any]]:
    inventories = {
        "V1": _git_json("v0.1.0", "artifact/attribute-inventory.json"),
        "V2": json.loads(Path("artifact/attribute-inventory.json").read_text(encoding="utf-8")),
    }
    validators = {
        "V1": _validator(_git_json("v0.1.0", "src/qmill_quantum_provenance/openapi.json")),
        "V2": _validator(
            json.loads(
                Path("src/qmill_quantum_provenance/openapi.json").read_text(encoding="utf-8")
            )
        ),
    }
    plan: list[tuple[str, str, str, Any, dict[str, Any] | None]] = []
    bases = {}
    for name, rel in BASES.items():
        base = json.loads((captures / rel / "fixture.json").read_text(encoding="utf-8"))
        bases[name] = base
        plan.append((name, "base", "base", None, base))
        for family, case, spec in cases():
            plan.append((name, family, case, spec, mutate(base, family, spec)))

    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for index, (_, _, _, _, fixture) in enumerate(plan):
            path = Path(tmp) / f"{index:05d}.json"
            if fixture is not None:
                path.write_text(json.dumps(fixture), encoding="utf-8")
            paths.append(path)
        v1 = tagged_records("v0.1.0", [p for p in paths if p.exists()])
        records = {
            "V1": [v1.get(str(p)) if p.exists() else None for p in paths],
            "V2": [_v2_record(f) if f is not None else None for (*_, f) in plan],
        }

    rows = []
    base_index = {name: i for i, (name, family, *_rest) in enumerate(plan) if family == "base"}
    for index, (name, family, case, spec, fixture) in enumerate(plan):
        if family == "base":
            continue
        row = {"base": name, "family": family, "case": case}
        if fixture is None:
            row["arms"] = "not_applicable"
            rows.append(row)
            continue
        provider = bases[name]["provider"]
        row["arms"] = {}
        for arm in ("V1", "V2"):
            if arm == "V1" and provider == "quandela":
                row["arms"][arm] = {"not_supported": True}
                continue
            base_record = records[arm][base_index[name]]
            row["arms"][arm] = measure(
                records[arm][index],
                base_record,
                inventories[arm],
                validators[arm],
                provider,
                family,
                spec,
            )
        rows.append(row)
    return rows
