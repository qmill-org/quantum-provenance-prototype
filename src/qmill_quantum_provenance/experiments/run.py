"""Run the failure-injection experiments (protocols/failure-injection.md).

python -m qmill_quantum_provenance.experiments.run --output artifact/failure-injection.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .drift import run_stage_c
from .seam import run_stage_b
from .transport import run_stage_a

MEASURES = ("M1_crash", "M3_valid", "M4_honest", "M5_reason", "M6_isolated", "M7_signal")


def summarize_a(cells: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, Counter] = defaultdict(Counter)
    for cell in cells:
        summary[cell["provider"]][cell["outcome"]] += 1
    return {provider: dict(counts) for provider, counts in sorted(summary.items())}


def summarize_b(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        if row["arms"] == "not_applicable":
            continue
        for arm, measured in row["arms"].items():
            if measured.get("not_supported"):
                continue
            counts = summary[arm][row["family"]]
            counts["cases"] += 1
            for measure in MEASURES:
                if measure in measured:
                    counts[f"{measure}={'yes' if measured[measure] else 'no'}"] += 1
    return {
        arm: {family: dict(sorted(c.items())) for family, c in fams.items()}
        for arm, fams in sorted(summary.items())
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "### Stage A (transport faults, V2 retrieval layers)",
        "",
        "| Provider | as expected | other integration error | escaped | n/a |",
        "|---|---|---|---|---|",
    ]
    for provider, counts in report["stage_a"]["summary"].items():
        lines.append(
            f"| {provider} | {counts.get('as_expected', 0)} | "
            f"{counts.get('other_integration_error', 0)} | {counts.get('escaped', 0)} | "
            f"{counts.get('not_applicable', 0)} |"
        )
    lines += [
        "",
        "### Stage B (seam faults): failing cases per measure",
        "",
        "| Arm | Family | cases | crash | invalid | fabricated | wrong reason | "
        "not isolated | no signal |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, families in report["stage_b"]["summary"].items():
        for family, c in families.items():
            lines.append(
                f"| {arm} | {family} | {c['cases']} | {c.get('M1_crash=yes', 0)} | "
                f"{c.get('M3_valid=no', 0)} | {c.get('M4_honest=no', 0)} | "
                f"{c.get('M5_reason=no', 0)} | {c.get('M6_isolated=no', 0)} | "
                f"{c.get('M7_signal=no', 0)} |"
            )
    lines += [
        "",
        "### Stage C (real interface change: IonQ run duration)",
        "",
        "| Response | V1 | V2 |",
        "|---|---|---|",
    ]
    for name, arms in report["stage_c"]["ionq_run_duration"].items():
        lines.append(f"| {name} | {arms['V1']} | {arms['V2']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--captures", type=Path, default=Path("captures"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cells = run_stage_a()
    rows = run_stage_b(args.captures)
    report = {
        "protocol": "protocols/failure-injection.md",
        "revision": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "stage_a": {"summary": summarize_a(cells), "cells": cells},
        "stage_b": {"summary": summarize_b(rows), "rows": rows},
        "stage_c": run_stage_c(Path(".")),
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
