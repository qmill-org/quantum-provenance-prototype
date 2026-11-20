"""Evaluation harness: attribute classification over the real evaluation captures."""

from __future__ import annotations

from qmill_quantum_provenance.evaluation import (
    _default_fixture_paths,
    classify_inventory,
    evaluate,
    load_inventory,
    main,
)


def _default_report() -> dict:
    return evaluate(_default_fixture_paths())


def _by_attribute() -> dict[str, dict[str, str]]:
    return {
        provider: rep["inventory_classification"]["by_attribute"]
        for provider, rep in _default_report()["providers"].items()
    }


def test_every_inventory_attribute_is_classified_per_provider() -> None:
    inventory_ids = {attr["id"] for attr in load_inventory()["attributes"]}
    for provider, rep in _default_report()["providers"].items():
        by_attribute = rep["inventory_classification"]["by_attribute"]
        assert set(by_attribute) == inventory_ids, provider
        assert rep["inventory_classification"]["unclassified"] == 0, provider
        assert "unclassified" not in by_attribute.values(), provider


def test_inventory_distinguishes_not_applicable_from_unavailable() -> None:
    by = _by_attribute()
    # Each record uses exactly the result representation the provider returned.
    assert by["ibm"]["results.measurement_counts"] == "provider_supplied"
    assert by["ibm"]["results.measurement_probabilities"] == "not_applicable"
    assert by["ionq"]["results.measurement_probabilities"] == "provider_supplied"
    assert by["ionq"]["results.measurement_counts"] == "not_applicable"
    # IonQ hardware via Braket: probabilities relayed, never presented as counts (F3).
    assert by["braket"]["results.measurement_probabilities"] == "provider_passthrough"
    assert by["braket"]["results.measurement_counts"] == "not_applicable"
    assert by["braket"]["results.estimated_measurement_counts"] == "derived"
    # Simulators have no hardware characterization; an applicable absence is unavailable.
    assert by["ionq"]["characterization"] == "not_applicable"
    assert by["braket"]["execution.queue_duration_ms"] == "unavailable"


def test_application_context_comes_from_the_run_ledgers() -> None:
    by = _by_attribute()
    assert by["ibm"]["compilation.compiler"] == "application_captured"
    assert by["ibm"]["compilation.logical_to_physical_mapping"] == "application_captured"
    for provider in by:
        assert by[provider]["software.provider_client"] == "application_captured"
    # Quandela does not record the requested samples; the application supplies them.
    assert by["quandela"]["job.shots"] == "application_captured"


def test_evaluate_report_shape_and_metrics() -> None:
    report = _default_report()
    assert report["report_format"] == "qmill.provenance.evaluation"
    assert report["attribute_inventory_version"] == load_inventory()["inventory_version"]
    assert report["shared_provider_independent_implementation_loc_total"] > 0
    assert set(report["providers"]) == {"braket", "ibm", "ionq", "quandela"}
    assert set(report["experiments"]) == {
        "baseline_comparison",
        "failure_injection",
        "live_validation",
    }


def test_classify_inventory_flags_unqualified_emitted_attribute() -> None:
    inventory = {
        "inventory_version": "test",
        "attributes": [
            {
                "id": "job.shots",
                "value_pointer": "/job/shots",
                "evidence_pointer": "/job/shots",
                "applicability": "all",
            }
        ],
    }
    # A record whose value is present but carries no matching evidence entry.
    payload = {"job": {"shots": 1000}, "evidence": [], "artifacts": []}
    result = classify_inventory(payload, inventory, "braket")
    assert result["job.shots"] == "unclassified"


def test_committed_evaluation_results_are_up_to_date() -> None:
    # The checked-in evaluation-results.json must match a freshly generated report.
    assert main(["--check"]) == 0
