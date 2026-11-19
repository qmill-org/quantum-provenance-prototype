"""Submit the purpose-run Quandela jobs through Perceval (WP-E3).

Usage::

    python scripts/run_quandela_jobs.py sim:belenos            # dry run
    python scripts/run_quandela_jobs.py sim:belenos --submit   # submit

Two linear-optical experiments: a two-mode Hong–Ou–Mandel test (balanced beam
splitter, input |1,1>) and a four-mode interferometer (input |1,0,1,0>). Each
submission is appended to ``runs/ledger-quandela.jsonl`` with the
application-captured context: the serialized experiment and its digest, input
state, post-selection, requested samples and shots, and client versions. Keys
already in the ledger for the same platform are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import perceval as pcvl
from perceval.algorithm import Sampler
from perceval.serialization import serialize

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "runs" / "ledger-quandela.jsonl"
MAX_SAMPLES = 1000
MAX_SHOTS = 100_000


def hom2() -> tuple[pcvl.Circuit, pcvl.BasicState]:
    return pcvl.BS(), pcvl.BasicState([1, 1])


def interferometer4() -> tuple[pcvl.Circuit, pcvl.BasicState]:
    circuit = pcvl.Circuit(4)
    circuit.add(0, pcvl.BS()).add(2, pcvl.BS()).add(1, pcvl.PS(0.7)).add(1, pcvl.BS())
    circuit.add(0, pcvl.BS()).add(2, pcvl.BS())
    return circuit, pcvl.BasicState([1, 0, 1, 0])


EXPERIMENTS = {"hom2": hom2, "interferometer4": interferometer4}


def _done(platform_name: str) -> set[str]:
    if not LEDGER.exists():
        return set()
    entries = [json.loads(line) for line in LEDGER.read_text().splitlines() if line]
    return {e["key"] for e in entries if e["platform"] == platform_name and e.get("job_id")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("platform")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    done = _done(args.platform)

    for name, build in EXPERIMENTS.items():
        key = f"e3-quandela-{args.platform.replace(':', '-')}-{name}"
        if args.only and name not in args.only:
            continue
        if key in done:
            print(f"{key}: already in ledger, skipping")
            continue
        circuit, input_state = build()
        serialized = serialize(circuit)
        print(f"{key}: {circuit.m} modes, input {input_state}, {MAX_SAMPLES} samples")
        if not args.submit:
            continue

        processor = pcvl.RemoteProcessor(args.platform, token=os.environ["QUANDELA_TOKEN"])
        processor.set_circuit(circuit)
        processor.with_input(input_state)
        processor.min_detected_photons_filter(input_state.n)
        sampler = Sampler(processor, max_shots_per_call=MAX_SHOTS)
        entry = {
            "key": key,
            "platform": args.platform,
            "submitted_at": datetime.now(UTC).isoformat(),
            "command": "sample_count",
            "max_samples": MAX_SAMPLES,
            "max_shots": MAX_SHOTS,
            "application_context": {
                "experiment": {
                    "builder": f"scripts/run_quandela_jobs.py:{name}",
                    "serialized_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
                    "modes": circuit.m,
                    "input_state": str(input_state),
                    "min_detected_photons": input_state.n,
                },
                "software": {
                    "python": platform.python_version(),
                    "perceval-quandela": version("perceval-quandela"),
                },
            },
        }
        try:
            job = sampler.sample_count.execute_async(MAX_SAMPLES)
            entry["job_id"] = job.id
        except Exception as exc:
            entry["error"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
        with LEDGER.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        print(f"  -> {entry.get('job_id') or entry.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
