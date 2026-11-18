"""Submit the purpose-run Amazon Braket jobs of a run plan, within a budget.

Usage::

    python scripts/run_purpose_jobs.py runs/plan-e2.json            # dry run
    python scripts/run_purpose_jobs.py runs/plan-e2.json --submit   # submit

Each attempt is appended to ``runs/ledger.jsonl`` together with the
application-captured context a submitting application would hold (program
digest, client and runtime versions, submission time). Account identifiers are
masked in the ledger. Jobs already created according to the ledger are skipped,
and the plan budget covers the estimated cost of every created job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import uuid
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import boto3

from qmill_quantum_provenance.live.sanitize import mask_identifiers

TASK_FEE_USD = 0.30
ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ROOT / "runs" / "programs"
LEDGER = ROOT / "runs" / "ledger.jsonl"


def _ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]


def _append(entry: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


def _action(program_file: str) -> tuple[str, str]:
    text = (PROGRAMS / program_file).read_text(encoding="utf-8")
    if program_file.endswith(".qasm"):
        action = {
            "braketSchemaHeader": {"name": "braket.ir.openqasm.program", "version": "1"},
            "source": text,
        }
        return json.dumps(action), text
    return json.dumps(json.loads(text)), text


def _price(client, device_arn: str) -> tuple[float, str, str]:
    device = client.get_device(deviceArn=device_arn)
    cost = json.loads(device["deviceCapabilities"]).get("service", {}).get("deviceCost") or {}
    if cost.get("unit") != "shot":
        raise SystemExit(f"{device_arn}: unsupported pricing unit {cost}")
    return float(cost["price"]), device["deviceStatus"], device["deviceName"]


def _git_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    account = boto3.client("sts").get_caller_identity()["Account"]
    created = {e["key"]: e for e in _ledger() if e.get("outcome") == "created"}
    committed = sum(e["estimated_cost_usd"] for e in created.values())
    software = {
        "python": platform.python_version(),
        "boto3": version("boto3"),
        "botocore": version("botocore"),
        "run_script_revision": _git_revision(),
        "client_side_compilation": None,
    }

    for job in plan["jobs"]:
        if args.only and job["key"] not in args.only:
            continue
        if job["key"] in created:
            print(f"{job['key']}: already created, skipping")
            continue
        region = job["device"].split(":")[3]
        braket = boto3.client("braket", region_name=region)
        price, status, name = _price(braket, job["device"])
        estimate = round(TASK_FEE_USD + price * job["shots"], 4)
        if committed + estimate > plan["budget_usd"]:
            print(f"{job['key']}: would exceed budget ({committed:.2f} + {estimate:.2f}), stopping")
            break
        action, program_text = _action(job["program"])
        print(f"{job['key']}: {name} [{status}] {job['shots']} shots, est ${estimate:.2f}")
        if not args.submit:
            continue

        entry = {
            "key": job["key"],
            "device": job["device"],
            "device_status_at_submit": status,
            "shots": job["shots"],
            "estimated_cost_usd": estimate,
            "submitted_at": datetime.now(UTC).isoformat(),
            "application_context": {
                "source_program": {
                    "reference": f"runs/programs/{job['program']}",
                    "sha256": hashlib.sha256(program_text.encode("utf-8")).hexdigest(),
                },
                "software": software,
            },
        }
        try:
            response = braket.create_quantum_task(
                clientToken=str(uuid.uuid4()),
                deviceArn=job["device"],
                shots=job["shots"],
                action=action,
                outputS3Bucket=f"amazon-braket-{region}-{account}",
                outputS3KeyPrefix=plan["output_prefix"],
                tags={"project": "quantum-provenance", "plan-key": job["key"]},
            )
            entry["outcome"] = "created"
            entry["task_arn"] = mask_identifiers(response["quantumTaskArn"])
            committed += estimate
            if job.get("cancel_after_submit"):
                cancel = braket.cancel_quantum_task(
                    quantumTaskArn=response["quantumTaskArn"], clientToken=str(uuid.uuid4())
                )
                entry["cancel_requested_at"] = datetime.now(UTC).isoformat()
                entry["cancel_state"] = cancel.get("cancellationStatus")
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
            entry["outcome"] = "rejected"
            entry["error"] = {"code": code, "message": mask_identifiers(str(exc))}
        _append(entry)
        print(f"  -> {entry['outcome']} {entry.get('task_arn') or entry.get('error')}")

    print(f"estimated committed spend: ${committed:.2f} of ${plan['budget_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
