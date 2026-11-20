"""WP-E4: oracle, baseline and readers on real captures (arms B and V2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qmill_quantum_provenance.comparison.baseline import flat_record
from qmill_quantum_provenance.comparison.oracle import load_ledgers, truth
from qmill_quantum_provenance.comparison.readers import read_baseline, read_contract, score
from qmill_quantum_provenance.comparison.run import v2_record

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "captures"
DIRECTORIES = sorted(path.parent for path in CAPTURES.glob("*/*/fixture.json"))
LEDGERS = load_ledgers(ROOT / "runs")


def _scores(directory: Path, arm: str) -> dict[str, str]:
    fixture = json.loads((directory / "fixture.json").read_text())
    record = flat_record(fixture) if arm == "B" else v2_record(fixture)
    expected = truth(directory, LEDGERS)
    if record is None:
        return {question: "no_record" for question in expected}
    answers = read_baseline(record) if arm == "B" else read_contract(record)
    return {q: score(answers.get(q), value, q) for q, value in expected.items() if q != "Q0"}


@pytest.mark.parametrize("directory", DIRECTORIES, ids=lambda p: f"{p.parent.name}/{p.name[:8]}")
def test_revised_records_never_mislead_on_the_development_set(directory: Path) -> None:
    assert "misleading" not in _scores(directory, "V2").values()


def test_baseline_presents_relayed_probabilities_as_observed_counts() -> None:
    scores = _scores(CAPTURES / "braket" / "c5f722a5-ee93-443e-8d89-f7ab285d7f69", "B")
    assert scores["Q1"] == "misleading" and scores["Q4"] == "misleading"


def test_baseline_has_no_record_for_a_job_the_provider_no_longer_returns() -> None:
    directory = CAPTURES / "braket" / "04470467-2658-4b06-8e5c-35b841c7b054"
    assert set(_scores(directory, "B").values()) == {"no_record"}
    assert _scores(directory, "V2")["Q5"] == "correct"


def test_oracle_reads_the_ibm_batch_and_client_side_estimator() -> None:
    batch = truth(CAPTURES / "ibm" / "dbvb20s1qo7s73ejeii0", LEDGERS)
    assert batch["Q8"].startswith("batch:") and batch["Q2"] == "application"
    estimator = truth(CAPTURES / "ibm" / "dbvb21mppgvc73e5o390", LEDGERS)
    assert (estimator["Q1"], estimator["Q6"], estimator["Q7"]) == ("client_derived", 1000, 2048)
