"""Submit the purpose-run IonQ jobs (direct API v0.4, free simulators).

Usage::

    python scripts/run_ionq_jobs.py            # dry run
    python scripts/run_ionq_jobs.py --submit   # submit

The program files (Braket OpenQASM 3 dialect: ``h``, ``cnot``, ``measure``) are
converted on the application side into IonQ's ``ionq.circuit.v1`` JSON with the
``qis`` gate set; the conversion and both digests are recorded in
``runs/ledger-ionq.jsonl``. Jobs already in the ledger are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ROOT / "runs" / "programs"
LEDGER = ROOT / "runs" / "ledger-ionq.jsonl"
API = "https://api.ionq.co/v0.4"
SHOTS = 1000

JOBS = [
    {"key": "e2-ionq-sim-bell2", "program": "bell2.qasm", "noise": None},
    {"key": "e2-ionq-noisy-forte1-ghz5", "program": "ghz5.qasm", "noise": {"model": "forte-1"}},
    {"key": "e5-ionq-invalid-gate", "program": "bell2.qasm", "noise": None, "corrupt": True},
]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_ionq_circuit(source: str) -> dict:
    """Convert the h/cnot subset of the Braket dialect to ionq.circuit.v1 (qis)."""

    qubits = int(re.search(r"qubit\[(\d+)\]", source).group(1))
    gates = []
    for line in source.splitlines():
        line = line.strip().rstrip(";")
        if m := re.fullmatch(r"h q\[(\d+)\]", line):
            gates.append({"gate": "h", "target": int(m.group(1))})
        elif m := re.fullmatch(r"cnot q\[(\d+)\], q\[(\d+)\]", line):
            gates.append({"gate": "cnot", "control": int(m.group(1)), "target": int(m.group(2))})
    return {"gateset": "qis", "qubits": qubits, "circuit": gates}


def _done() -> set[str]:
    if not LEDGER.exists():
        return set()
    return {json.loads(line)["key"] for line in LEDGER.read_text().splitlines() if line}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    headers = {"Authorization": f"apiKey {os.environ['IONQ_API_KEY']}"}
    done = _done()

    for job in JOBS:
        if job["key"] in done:
            print(f"{job['key']}: already in ledger, skipping")
            continue
        source = (PROGRAMS / job["program"]).read_text(encoding="utf-8")
        circuit = to_ionq_circuit(source)
        if job.get("corrupt"):
            circuit["circuit"][0]["gate"] = "not_a_gate"
        payload = {
            "type": "ionq.circuit.v1",
            "name": job["key"],
            "backend": "simulator",
            "shots": SHOTS,
            "input": circuit,
        }
        if job["noise"]:
            payload["noise"] = job["noise"]
        converted = json.dumps(circuit, sort_keys=True)
        print(f"{job['key']}: {len(circuit['circuit'])} gates, noise={job['noise']}")
        if not args.submit:
            continue

        response = httpx.post(f"{API}/jobs", headers=headers, json=payload, timeout=60)
        entry = {
            "key": job["key"],
            "backend": "simulator",
            "noise": job["noise"],
            "shots": SHOTS,
            "submitted_at": datetime.now(UTC).isoformat(),
            "http_status": response.status_code,
            "application_context": {
                "source_program": {
                    "reference": f"runs/programs/{job['program']}",
                    "sha256": _digest(source),
                    "dialect": "braket-openqasm3",
                },
                "converted_program": {
                    "format": "ionq.circuit.v1 (qis)",
                    "sha256": _digest(converted),
                    "conversion": "scripts/run_ionq_jobs.py:to_ionq_circuit"
                    + ("; first gate deliberately invalid" if job.get("corrupt") else ""),
                },
                "software": {"python": platform.python_version(), "httpx": version("httpx")},
            },
        }
        body = response.json() if response.content else {}
        if response.is_success:
            entry["job_id"] = body.get("id")
        else:
            entry["error"] = body
        with LEDGER.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        print(f"  -> HTTP {response.status_code} {entry.get('job_id') or entry.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
