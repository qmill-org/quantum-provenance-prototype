"""Schema-change experiment in the provenance evaluation harness.

Verifies that the additive schema change is backward compatible against every
shipped example record and that a record carrying the new attribute is rejected
by the canonical contract but accepted once the schema is extended.
"""

from __future__ import annotations

from pathlib import Path

from qmill_quantum_provenance.evaluation import (
    classify_inventory,
    evaluate,
    load_inventory,
    main,
    run_partial_record_experiment,
    run_provider_input_experiment,
    run_schema_change_experiment,
)


def _default_report() -> dict:
    root = Path(__file__).resolve().parent
    fixtures = root / "fixtures"
    return evaluate(
        {
            "braket": fixtures / "braket" / "completed.json",
            "ibm": fixtures / "ibm" / "completed.json",
            "ionq": fixtures / "ionq" / "completed.json",
        }
    )


def test_additive_change_is_backward_compatible_and_necessary() -> None:
    result = run_schema_change_experiment()

    assert result["change"]["type"] == "additive_optional_attribute"
    assert result["change"]["attribute"] == "cost"

    measured = result["measured"]
    assert measured["examples_checked"] >= 3
    assert measured["backward_compatible"] is True
    assert measured["new_attribute_rejected_by_original"] is True
    assert measured["new_attribute_accepted_by_extended"] is True
    assert measured["change_is_necessary"] is True

    # Every shipped example stays valid under both the original and extended
    # contracts (the change adds no required field).
    for item in measured["per_example"]:
        assert item["valid_original"] is True
        assert item["valid_extended"] is True


def test_touch_set_reports_shared_and_unchanged_infrastructure() -> None:
    result = run_schema_change_experiment()
    touch = result["touch_set"]

    assert touch["shared_implementation_files"] == len(touch["shared_implementation"])
    # The seam infrastructure that dispatches to adapters is not touched by a
    # new attribute.
    assert "src/qmill_quantum_provenance/registry.py" in touch["unchanged_infrastructure"]
    assert "src/qmill_quantum_provenance/replay.py" in touch["unchanged_infrastructure"]
    assert "src/qmill_quantum_provenance/contract.py" in touch["unchanged_infrastructure"]


def test_evaluate_embeds_schema_change_experiment() -> None:
    root = Path(__file__).resolve().parent
    fixtures = root / "fixtures"
    report = evaluate(
        {
            "braket": fixtures / "braket" / "completed.json",
            "ibm": fixtures / "ibm" / "completed.json",
            "ionq": fixtures / "ionq" / "completed.json",
        }
    )

    experiment = report["schema_change_experiment"]
    assert experiment["measured"]["backward_compatible"] is True
    assert experiment["measured"]["change_is_necessary"] is True


def test_provider_input_change_is_isolated() -> None:
    result = run_provider_input_experiment()

    assert result["change"]["type"] == "provider_input_field_rename"
    assert result["change"]["provider"] == "ibm"
    assert result["change"]["affected_attribute"] == "/device/qubit_count"

    measured = result["measured"]
    # The IBM record still validates after the upstream field is renamed.
    assert measured["ibm_record_still_validates"] is True
    # The attribute was present before and degrades to unavailable after.
    assert measured["qubit_count_before"] is not None
    assert measured["qubit_count_after"] is None
    assert measured["affected_attribute_status_after"] == "unavailable"
    assert measured["affected_attribute_degraded_to_unavailable"] is True
    # Braket and IonQ records are byte-for-byte unchanged.
    assert measured["other_providers_unchanged"] == {"braket": True, "ionq": True}
    assert measured["isolation_holds"] is True


def test_provider_input_touch_set_is_single_adapter() -> None:
    result = run_provider_input_experiment()
    touch = result["touch_set"]

    assert touch["files"] == 1
    assert touch["to_restore_attribute"] == ["src/qmill_quantum_provenance/adapters/ibm.py"]


def test_evaluate_embeds_provider_input_experiment() -> None:
    root = Path(__file__).resolve().parent
    fixtures = root / "fixtures"
    report = evaluate(
        {
            "braket": fixtures / "braket" / "completed.json",
            "ibm": fixtures / "ibm" / "completed.json",
            "ionq": fixtures / "ionq" / "completed.json",
        }
    )

    experiment = report["provider_input_experiment"]
    assert experiment["measured"]["isolation_holds"] is True
    assert experiment["touch_set"]["files"] == 1


def test_every_inventory_attribute_is_classified_per_provider() -> None:
    inventory = load_inventory()
    inventory_ids = {attr["id"] for attr in inventory["attributes"]}
    report = _default_report()

    for provider, rep in report["providers"].items():
        by_attribute = rep["inventory_classification"]["by_attribute"]
        # Every fixed inventory item receives exactly one classification.
        assert set(by_attribute) == inventory_ids, provider
        # No applicable emitted attribute is left unclassified.
        assert rep["inventory_classification"]["unclassified"] == 0, provider
        assert "unclassified" not in by_attribute.values(), provider


def test_inventory_distinguishes_not_applicable_from_unavailable() -> None:
    report = _default_report()
    braket = report["providers"]["braket"]["inventory_classification"]["by_attribute"]
    ionq = report["providers"]["ionq"]["inventory_classification"]["by_attribute"]

    # IonQ returns probabilities, so observed counts are inapplicable there;
    # probabilities are inapplicable for the count-returning providers.
    assert ionq["results.measurement_counts"] == "not_applicable"
    assert braket["results.measurement_probabilities"] == "not_applicable"
    assert ionq["results.measurement_probabilities"] == "provider_supplied"
    assert braket["results.measurement_counts"] == "provider_supplied"

    # An applicable-but-absent field is unavailable (not not_applicable).
    assert braket["execution.queue_duration_ms"] == "unavailable"


def test_application_captured_context_present_for_principal_cases() -> None:
    report = _default_report()
    for provider in ("braket", "ibm"):
        by_attribute = report["providers"][provider]["inventory_classification"]["by_attribute"]
        assert by_attribute["compilation.compiler"] == "application_captured"
        assert by_attribute["compilation.logical_to_physical_mapping"] == "application_captured"
        assert by_attribute["software.provider_client"] == "application_captured"
        assert by_attribute["software.framework_versions"] == "application_captured"


def test_partial_record_experiment_degrades_gracefully() -> None:
    result = run_partial_record_experiment()

    measured = result["measured"]
    assert measured["all_records_validate"] is True
    assert measured["characterization_degrades_everywhere"] is True
    assert measured["no_unclassified_attributes"] is True
    for provider in ("braket", "ibm", "ionq"):
        assert measured["per_provider"][provider]["characterization_unavailable"] is True


def test_evaluate_report_shape_and_metrics() -> None:
    report = _default_report()

    assert report["report_format"] == "qmill.provenance.evaluation"
    assert report["report_version"]
    assert report["attribute_inventory_version"] == load_inventory()["inventory_version"]
    # Shared LOC is reported under the provider-independent implementation key.
    assert "shared_provider_independent_implementation_loc" in report
    assert report["shared_provider_independent_implementation_loc_total"] > 0
    assert "partial_record_experiment" in report


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
