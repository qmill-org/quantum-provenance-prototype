"""Submit the purpose-run IBM Quantum jobs (WP-E2) and record application context.

Usage::

    python scripts/run_ibm_jobs.py ibm_aachen            # dry run
    python scripts/run_ibm_jobs.py ibm_aachen --submit   # submit

Circuits are compiled here, on the application side, with a recorded seed and
optimization level, then submitted as ISA circuits to Sampler/Estimator V2.
Each submission is appended to ``runs/ledger-ibm.jsonl`` with the
application-captured context (source and converted program digests, compiler
version, optimization level, seed, layout). Jobs already in the ledger are
skipped.

The program files use the Amazon Braket OpenQASM 3 dialect (built-in ``h``
and ``cnot``, no ``stdgates.inc``). For Qiskit they are converted by adding
``include "stdgates.inc";`` and renaming ``cnot`` to ``cx``; both digests are
recorded.
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

from qiskit import qasm3
from qiskit.quantum_info import SparsePauliOp
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime import Batch, EstimatorV2, QiskitRuntimeService, SamplerV2

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ROOT / "runs" / "programs"
LEDGER = ROOT / "runs" / "ledger-ibm.jsonl"
SEED = 1234

JOBS = [
    {"key": "e2-ibm-sampler-bell2", "program": "bell2.qasm", "kind": "sampler", "opt": 2},
    {"key": "e2-ibm-sampler-ghz5", "program": "ghz5.qasm", "kind": "sampler", "opt": 2},
    {"key": "e2-ibm-batch-bell2-o0", "program": "bell2.qasm", "kind": "batch", "opt": 0},
    {"key": "e2-ibm-batch-bell2-o1", "program": "bell2.qasm", "kind": "batch", "opt": 1},
    {"key": "e2-ibm-batch-bell2-o3", "program": "bell2.qasm", "kind": "batch", "opt": 3},
    {"key": "e2-ibm-estimator-bell2-zz", "program": "bell2.qasm", "kind": "estimator", "opt": 2},
    {"key": "e5-ibm-sampler-cancelled", "program": "bell2.qasm", "kind": "cancel", "opt": 2},
    # Hold-out set H1 (protocols/baseline-comparison.md).
    {
        "key": "h1-ibm-sampler-ghz5-twirled",
        "program": "ghz5.qasm",
        "kind": "sampler_twirled",
        "opt": 2,
    },
    {
        "key": "h1-ibm-estimator-ghz5-r0",
        "program": "ghz5.qasm",
        "kind": "estimator",
        "opt": 2,
        "observable": "IIIZZ",
        "resilience_level": 0,
    },
]
SHOTS = 1000


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _to_qiskit_dialect(source: str) -> str:
    body = re.sub(r"\bcnot\b", "cx", source)
    return body.replace("OPENQASM 3.0;", 'OPENQASM 3.0;\ninclude "stdgates.inc";', 1)


def _done_keys() -> set[str]:
    if not LEDGER.exists():
        return set()
    return {json.loads(line)["key"] for line in LEDGER.read_text().splitlines() if line}


def _append(entry: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("backend")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--only", nargs="*", help="submit only these keys")
    args = parser.parse_args()

    service = QiskitRuntimeService(
        channel="ibm_quantum_platform",
        token=os.environ["IBM_QUANTUM_API_KEY"],
        instance=os.environ["IBM_QUANTUM_INSTANCE_CRN"],
    )
    backend = service.backend(args.backend)
    done = _done_keys()
    software = {
        "python": platform.python_version(),
        "qiskit": version("qiskit"),
        "qiskit-ibm-runtime": version("qiskit-ibm-runtime"),
    }

    prepared = []
    for job in JOBS:
        if args.only and job["key"] not in args.only:
            continue
        if job["key"] in done:
            print(f"{job['key']}: already in ledger, skipping")
            continue
        source = (PROGRAMS / job["program"]).read_text(encoding="utf-8")
        converted = _to_qiskit_dialect(source)
        circuit = qasm3.loads(converted)
        pass_manager = generate_preset_pass_manager(
            optimization_level=job["opt"], backend=backend, seed_transpiler=SEED
        )
        isa = pass_manager.run(circuit)
        layout = isa.layout.final_index_layout() if isa.layout else None
        context = {
            "source_program": {
                "reference": f"runs/programs/{job['program']}",
                "sha256": _digest(source),
                "dialect": "braket-openqasm3",
            },
            "converted_program": {
                "sha256": _digest(converted),
                "conversion": 'add include "stdgates.inc"; rename cnot to cx',
            },
            "compilation": {
                "compiler": "qiskit preset pass manager",
                "compiler_version": version("qiskit"),
                "optimization_level": job["opt"],
                "seed_transpiler": SEED,
                "final_layout": layout,
                "isa_depth": isa.depth(),
                "isa_ops": dict(isa.count_ops()),
            },
            "software": software,
        }
        prepared.append((job, isa, context))
        print(f"{job['key']}: {job['kind']} opt={job['opt']} layout={layout} depth={isa.depth()}")

    if not args.submit:
        return 0

    def record(job, context, runtime_job, mode_id=None, **extra):
        entry = {
            "key": job["key"],
            "backend": args.backend,
            "kind": job["kind"],
            "shots": SHOTS,
            "submitted_at": datetime.now(UTC).isoformat(),
            "job_id": runtime_job.job_id(),
            "mode_id": mode_id,
            "application_context": context,
            **extra,
        }
        _append(entry)
        print(f"  -> {job['key']}: {entry['job_id']} {extra or ''}")

    batch_jobs = [p for p in prepared if p[0]["kind"] == "batch"]
    if batch_jobs:
        with Batch(backend=backend) as batch:
            sampler = SamplerV2(mode=batch)
            for job, isa, context in batch_jobs:
                record(job, context, sampler.run([isa], shots=SHOTS), mode_id=batch.session_id)

    for job, isa, context in prepared:
        if job["kind"] in {"sampler", "cancel"}:
            runtime_job = SamplerV2(mode=backend).run([isa], shots=SHOTS)
            extra = {}
            if job["kind"] == "cancel":
                runtime_job.cancel()
                extra = {"cancel_requested_at": datetime.now(UTC).isoformat()}
            record(job, context, runtime_job, **extra)
        elif job["kind"] == "sampler_twirled":
            sampler = SamplerV2(mode=backend)
            sampler.options.twirling.enable_gates = True
            sampler.options.twirling.enable_measure = True
            record(job, context, sampler.run([isa], shots=SHOTS), twirling="gates+measure")
        elif job["kind"] == "estimator":
            label = job.get("observable", "ZZ")
            observable = SparsePauliOp(label).apply_layout(isa.layout)
            estimator = EstimatorV2(mode=backend)
            estimator.options.default_shots = SHOTS
            extra = {"observable": label}
            if "resilience_level" in job:
                estimator.options.resilience_level = job["resilience_level"]
                extra["resilience_level"] = job["resilience_level"]
            record(job, context, estimator.run([(isa, observable)]), **extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
