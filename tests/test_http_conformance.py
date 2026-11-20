"""WP-E6 S8: property-based contract conformance of the HTTP service (Schemathesis)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

schemathesis = pytest.importorskip("schemathesis")
from hypothesis import HealthCheck, settings  # noqa: E402

from qmill_quantum_provenance.server.app import create_app  # noqa: E402
from qmill_quantum_provenance.server.auth import KeyRing, hash_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEY = "key-conformance-4e2a9c"


@pytest.fixture
def api_schema(tmp_path):
    keys = tmp_path / "keys.json"
    keys.write_text(
        json.dumps([{"sha256": hash_key(KEY), "tenant": "t1", "permissions": ["read", "write"]}])
    )
    app = create_app(
        tmp_path / "db.sqlite", KeyRing.from_file(keys), mode="replay", captures=ROOT / "captures"
    )
    return schemathesis.openapi.from_asgi("/v1/openapi.json", app)


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@settings(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
def test_every_response_conforms_to_the_contract(case) -> None:
    case.call_and_validate(headers={"Authorization": f"Bearer {KEY}"})
