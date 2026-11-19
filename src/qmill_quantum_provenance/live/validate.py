"""Run provenance adapters over captured live responses and check their claims.

Usage::

    python -m qmill_quantum_provenance.live.validate captures/ [--report out.json]

For every capture the adapter of that provider builds a record through
:class:`ReplayIntegrationAdapter`, exactly as in the fixture evaluation but
without application-captured context. The record is validated against the
contract, classified with the attribute inventory, and checked against facts
recorded independently in the capture (``native.json`` / ``manifest.json``):

* ``derived_counts_labeled_provider_supplied`` -- counts were expanded from
  provider probabilities but the record marks them as provider-supplied;
* ``characterization_without_timestamp`` -- characterization is attached but
  has no observation timestamp, so its temporal association is unverifiable;
* ``characterization_postdates_job`` -- the snapshot was observed after the job
  ended (reported with the gap, whatever association the record claims);
* ``record_not_produced`` -- the service raised instead of returning a record;
* ``submitted_program_not_mapped`` -- the provider retains the submitted
  program but the record carries no ``submitted`` artifact;
* ``application_compiled_attributed_to_provider`` -- the compiled program was
  produced by the application (and only returned by the provider) but the
  record attributes it to the provider.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from ..adapter import CreateProvenanceRecordRequest
from ..contract import validate_record
from ..evaluation import build_service, classify_inventory, load_inventory


def _parse(value: Any) -> datetime | None:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _evidence(payload: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in payload.get("evidence", []):
        found.setdefault(item["path"], item["status"])
    return found


def check_claims(payload: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    evidence = _evidence(payload)

    notes = manifest.get("notes") or {}
    origin = notes.get("measurement_counts_origin")
    if (
        origin
        and origin.startswith("expanded")
        and (evidence.get("/results/measurement_counts") == "provider_supplied")
    ):
        findings.append(
            {
                "check": "derived_counts_labeled_provider_supplied",
                "detail": f"counts origin {origin!r}; record status provider_supplied",
            }
        )

    roles = {artifact.get("role") for artifact in payload.get("artifacts") or []}
    if notes.get("compiled_program_origin") == "application_compiled_job_input":
        artifacts = payload.get("artifacts") or []
        if not any(artifact.get("producer") == "application" for artifact in artifacts):
            statuses = sorted({evidence.get(f"/artifacts/{i}", "?") for i in range(len(artifacts))})
            findings.append(
                {
                    "check": "application_compiled_attributed_to_provider",
                    "detail": "program compiled by the application; no artifact names the "
                    f"application as producer (artifact evidence: {statuses})",
                }
            )

    if notes.get("submitted_program_available") and "submitted" not in roles:
        findings.append(
            {
                "check": "submitted_program_not_mapped",
                "detail": "provider retains the submitted program; record has no submitted artifact",
            }
        )

    characterization = payload.get("characterization") or {}
    if characterization:
        association = characterization.get("association")
        captured = _parse(characterization.get("captured_at"))
        ended = _parse((payload.get("job") or {}).get("ended_at"))
        if captured is None:
            findings.append(
                {
                    "check": "characterization_without_timestamp",
                    "detail": f"association {association!r} has no captured_at",
                }
            )
        elif ended is not None and captured > ended:
            findings.append(
                {
                    "check": "characterization_postdates_job",
                    "detail": f"association {association!r}; observed "
                    f"{(captured - ended).total_seconds() / 86400:.1f} days after job end",
                }
            )
    return findings


def validate_capture(directory: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    fixture = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    provider = fixture["provider"]
    entry: dict[str, Any] = {
        "capture": directory.name,
        "provider": provider,
        "upstream": {op["operation"]: op["outcome"] for op in manifest["operations"]},
    }
    try:
        service = build_service({provider: fixture})
        record, _ = service.create_record(
            CreateProvenanceRecordRequest(
                provider=provider,
                external_job_id=str(fixture["external_job_id"]),
                region=fixture.get("region"),
            )
        )
        payload = record.to_dict()
    except Exception as exc:
        entry["record"] = None
        entry["findings"] = [
            {
                "check": "record_not_produced",
                "detail": f"{type(exc).__name__}: {exc}",
                "raised_at": traceback.extract_tb(exc.__traceback__)[-1].name,
            }
        ]
        return entry

    try:
        validate_record(payload)
        entry["schema_valid"] = True
    except Exception as exc:
        entry["schema_valid"] = False
        entry["schema_error"] = str(exc).splitlines()[0]
    classes = classify_inventory(payload, inventory, provider)
    entry["inventory_counts"] = dict(sorted(Counter(classes.values()).items()))
    entry["inventory"] = dict(sorted(classes.items()))
    entry["device"] = {
        k: (payload.get("device") or {}).get(k)
        for k in ("identifier", "platform_provider", "hardware_provider")
    }
    entry["findings"] = check_claims(payload, manifest)
    return entry


def _adapter_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", "adapters"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("captures", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    inventory = load_inventory()
    entries = [
        validate_capture(path.parent, inventory)
        for path in sorted(args.captures.glob("*/*/fixture.json"))
    ]
    report = {
        "adapter_revision": _adapter_revision(),
        "inventory_version": inventory["inventory_version"],
        "captures": entries,
        "finding_counts": dict(
            sorted(Counter(f["check"] for e in entries for f in e["findings"]).items())
        ),
    }
    for entry in entries:
        checks = ", ".join(f["check"] for f in entry["findings"]) or "-"
        valid = entry.get("schema_valid", "n/a")
        print(f"{entry['provider']}/{entry['capture']}: schema_valid={valid}; findings: {checks}")
    print("finding counts:", report["finding_counts"])
    if args.report:
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
