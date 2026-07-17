"""Contract checks for the reduced Unified Quantum Provenance prototype."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import jsonschema

from qmill_quantum_provenance import CreateProvenanceRecordRequest
from qmill_quantum_provenance.contract import contract_path
from qmill_quantum_provenance.generate_examples import generate

_EXAMPLES_DIRECTORY = Path(__file__).resolve().parents[1] / "artifact" / "examples"


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def test_openapi_contract_is_reduced_to_two_operations() -> None:
    contract = _load_json(contract_path())

    assert contract["openapi"] == "3.1.0"
    assert contract["info"]["version"] == "0.1.0-prototype"
    assert "ProvenanceRecord" in contract["components"]["schemas"]

    paths = contract["paths"]
    assert set(paths) == {"/v1/provenance-records", "/v1/jobs/{job_id}/provenance"}
    assert "post" in paths["/v1/provenance-records"]
    assert "get" in paths["/v1/jobs/{job_id}/provenance"]


def test_provenance_examples_validate_against_canonical_record_schema() -> None:
    contract = _load_json(contract_path())
    resolver = jsonschema.RefResolver.from_schema(contract)
    validator = jsonschema.Draft202012Validator(
        contract["components"]["schemas"]["ProvenanceRecord"],
        resolver=resolver,
    )

    examples = sorted(_EXAMPLES_DIRECTORY.glob("*.json"))
    assert examples, "expected at least one canonical example record"

    for example_path in examples:
        validator.validate(_load_json(example_path))


def test_create_request_model_matches_openapi_schema() -> None:
    """The handwritten request model must not diverge from the contract."""

    contract = _load_json(contract_path())
    schema = contract["components"]["schemas"]["CreateProvenanceRecordRequest"]

    model_fields = {f.name for f in dataclasses.fields(CreateProvenanceRecordRequest)}
    contract_fields = set(schema["properties"])

    assert model_fields == contract_fields, (
        "CreateProvenanceRecordRequest diverges from the OpenAPI contract: "
        f"model-only={sorted(model_fields - contract_fields)} "
        f"contract-only={sorted(contract_fields - model_fields)}"
    )

    # Required fields in the contract must be non-defaulted fields in the model.
    required = set(schema.get("required", []))
    non_default = {
        f.name
        for f in dataclasses.fields(CreateProvenanceRecordRequest)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
    }
    assert required == non_default


def test_checked_in_example_records_are_up_to_date() -> None:
    """The committed example records must match current adapter output.

    Guards against regenerating the adapters/model without refreshing the
    example records under docs/. Volatile timestamps are ignored by the checker.
    """

    assert generate(check=True) == 0
