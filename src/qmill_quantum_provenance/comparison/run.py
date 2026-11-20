"""Run the baseline comparison over the captures (protocols/baseline-comparison.md).

    python -m qmill_quantum_provenance.comparison.run \
        --captures captures --runs runs --output artifact/baseline-comparison.json

Arm V1 runs the ``v0.1.0`` package from a temporary git worktree in a
subprocess; its replay is given the same rule as the current one (a recorded
provider error is raised), which changes the test harness, not the adapters.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..adapter import CreateProvenanceRecordRequest
from ..evaluation import build_service
from .baseline import flat_record
from .oracle import load_ledgers, parse_time, truth
from .readers import UNDETERMINABLE, read_baseline, read_contract, score

QUESTIONS = ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10", "N1", "N2", "N3")
OUTCOMES = ("correct", "misleading", "undeterminable", "no_record")
FREEZE_TAG = "baseline-freeze"

_V1_SCRIPT = r"""
import json, sys
from qmill_quantum_provenance import replay
from qmill_quantum_provenance import integration
from qmill_quantum_provenance.integration import ProviderIntegrationError
from qmill_quantum_provenance.evaluation import build_service
from qmill_quantum_provenance.adapter import CreateProvenanceRecordRequest

def _guard(name):
    original = getattr(replay.ReplayIntegrationAdapter, name)
    def wrapped(self, *args, **kwargs):
        recorded = (self._fixture.get("upstream_errors") or {}).get(name)
        if recorded:
            error = getattr(integration, str(recorded.get("error")), None)
            if not (isinstance(error, type) and issubclass(error, Exception)):
                error = ProviderIntegrationError
            raise error(str(recorded.get("message", "")))
        return original(self, *args, **kwargs)
    setattr(replay.ReplayIntegrationAdapter, name, wrapped)

for name in ("get_status", "get_result", "get_device_details"):
    _guard(name)

out = {}
for path in sys.argv[1:]:
    fixture = json.load(open(path))
    try:
        record, _ = build_service({fixture["provider"]: fixture}).create_record(
            CreateProvenanceRecordRequest(provider=fixture["provider"],
                external_job_id=fixture["external_job_id"], region=fixture.get("region")))
        out[path] = record.to_dict()
    except Exception as exc:
        out[path] = None
print(json.dumps(out, default=str))
"""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def v1_records(fixtures: list[Path]) -> dict[str, dict[str, Any] | None]:
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "v010"
        _git("worktree", "add", "--detach", str(tree), "v0.1.0")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _V1_SCRIPT, *map(str, fixtures)],
                check=True,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": str(tree / "src"), "PATH": ""},
            )
        finally:
            _git("worktree", "remove", "--force", str(tree))
    return json.loads(proc.stdout)


def v2_record(fixture: dict[str, Any]) -> dict[str, Any] | None:
    try:
        record, _ = build_service({fixture["provider"]: fixture}).create_record(
            CreateProvenanceRecordRequest(
                provider=fixture["provider"],
                external_job_id=fixture["external_job_id"],
                region=fixture.get("region"),
            )
        )
    except Exception:
        return None
    return record.to_dict()


def _freeze_time() -> datetime | None:
    try:
        return parse_time(_git("log", "-1", "--format=%cI", FREEZE_TAG))
    except subprocess.CalledProcessError:
        return None


def _answers(arm: str, record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {question: "no_record" for question in QUESTIONS}
    return read_baseline(record) if arm == "B" else read_contract(record)


def run(captures: Path, runs: Path) -> dict[str, Any]:
    directories = sorted(path.parent for path in captures.glob("*/*/fixture.json"))
    fixtures = [directory / "fixture.json" for directory in directories]
    v1 = v1_records(fixtures)
    ledgers = load_ledgers(runs)
    freeze = _freeze_time()
    rows = []
    summary: dict[str, dict[str, dict[str, Counter]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(Counter))
    )
    for directory, fixture_path in zip(directories, fixtures, strict=True):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        captured = parse_time(manifest.get("captured_at"))
        capture_set = "holdout" if freeze and captured and captured > freeze else "development"
        expected = truth(directory, ledgers)
        records = {
            "B": flat_record(fixture),
            "V1": v1.get(str(fixture_path)),
            "V2": v2_record(fixture),
        }
        row: dict[str, Any] = {
            "capture": f"{directory.parent.name}/{directory.name}",
            "set": capture_set,
            "truth": expected,
            "arms": {},
        }
        for arm, record in records.items():
            answers = _answers(arm, record)
            scores = {}
            for question, value in expected.items():
                answer = answers.get(question, UNDETERMINABLE)
                scores[question] = (
                    ("correct" if answer is True else "no_record")
                    if question == "Q0"
                    else score(answer, value, question)
                )
                summary[capture_set][arm][question][scores[question]] += 1
            row["arms"][arm] = {
                "answers": {q: answers.get(q) for q in expected},
                "scores": scores,
            }
        # Sensitivity: a cautious baseline consumer does not read `provider` as the operator.
        if "Q4" in expected:
            row["sensitivity"] = {"B_Q4_cautious": "undeterminable"}
        rows.append(row)
    return {
        "protocol": "protocols/baseline-comparison.md",
        "freeze_tag": FREEZE_TAG if freeze else None,
        "arms": {
            "B": "flat baseline (comparison/baseline.py)",
            "V1": "v0.1.0",
            "V2": _git("rev-parse", "--short", "HEAD"),
        },
        "summary": _render_summary(summary),
        "captures": rows,
    }


def _render_summary(summary) -> dict[str, Any]:
    rendered: dict[str, Any] = {}
    for capture_set, arms in summary.items():
        rendered[capture_set] = {}
        for arm, questions in sorted(arms.items()):
            totals: Counter = Counter()
            per_question = {}
            for question in QUESTIONS:
                if question in questions:
                    counts = questions[question]
                    per_question[question] = {o: counts.get(o, 0) for o in OUTCOMES}
                    totals.update(counts)
            rendered[capture_set][arm] = {
                "total": {o: totals.get(o, 0) for o in OUTCOMES},
                "per_question": per_question,
            }
    return rendered


def markdown(report: dict[str, Any]) -> str:
    lines = []
    for capture_set, arms in report["summary"].items():
        lines.append(f"### {capture_set}\n")
        lines.append("| Question | " + " | ".join(f"{a} c/m/u/n" for a in arms) + " |")
        lines.append("|---|" + "---|" * len(arms))
        questions = [q for q in QUESTIONS if any(q in v["per_question"] for v in arms.values())]
        for question in [*questions, "total"]:
            cells = []
            for data in arms.values():
                counts = data["total"] if question == "total" else data["per_question"][question]
                cells.append("/".join(str(counts[o]) for o in OUTCOMES))
            lines.append(f"| {question} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--captures", type=Path, default=Path("captures"))
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run(args.captures, args.runs)
    if args.output:
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=False, default=str) + "\n", encoding="utf-8"
        )
    print(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
