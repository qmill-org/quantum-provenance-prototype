"""WP-E6: reference HTTP service (protocols/http-service.md, S1-S7; S8 in test_http_conformance)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from qmill_quantum_provenance.server.app import create_app  # noqa: E402
from qmill_quantum_provenance.server.auth import KeyRing, hash_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IBM_JOB = "dbvb21eppgvc73e5o380"
IONQ_JOB = "01a1f2eb-d155-7632-bc4e-f340de096f01"
KEYS = {
    "a_rw": ("key-a-rw-7f3c9e1d2b", "tenant-a", ["read", "write"]),
    "a_ro": ("key-a-ro-5d8e2a6f0c", "tenant-a", ["read"]),
    "b_rw": ("key-b-rw-9a1b4c7e3d", "tenant-b", ["read", "write"]),
}
ENV_SECRETS = {
    "AWS_SECRET_ACCESS_KEY": "SENTINEL-aws-secret-0001",
    "IBM_QUANTUM_API_KEY": "SENTINEL-ibm-key-0002",
    "IONQ_API_KEY": "SENTINEL-ionq-key-0003",
    "QUANDELA_TOKEN": "SENTINEL-quandela-token-0004",
}
UPSTREAM_SECRET = "SENTINEL-upstream-token-0005"


def _auth(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {KEYS[name][0]}"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name, value in ENV_SECRETS.items():
        monkeypatch.setenv(name, value)
    captures = tmp_path / "captures"
    for rel in (f"ibm/{IBM_JOB}", f"ionq/{IONQ_JOB}"):
        shutil.copytree(ROOT / "captures" / rel, captures / rel)
    # A provider error whose message carries credentials, as some HTTP clients
    # include request headers or signed URLs in error text.
    leaky = json.loads((captures / "ionq" / IONQ_JOB / "fixture.json").read_text())
    leaky["external_job_id"] = "leaky-job"
    leaky["upstream_errors"] = {
        "get_result": {
            "error": "AccessDeniedError",
            "message": f"HTTP 403 for https://api.ionq.co/v0.4/jobs/x?token={UPSTREAM_SECRET} "
            f"with Authorization: apiKey {UPSTREAM_SECRET}",
        }
    }
    (captures / "ionq" / "leaky-job").mkdir()
    (captures / "ionq" / "leaky-job" / "fixture.json").write_text(json.dumps(leaky))
    keys_file = tmp_path / "keys.json"
    keys_file.write_text(
        json.dumps(
            [
                {"sha256": hash_key(key), "tenant": tenant, "permissions": perms}
                for key, tenant, perms in KEYS.values()
            ]
        )
    )
    db = tmp_path / "provenance.sqlite"
    app = create_app(db, KeyRing.from_file(keys_file), mode="replay", captures=captures)
    return TestClient(app), db, keys_file


def _create(client, key="a_rw", **body):
    payload = {"provider": "ibm", "external_job_id": IBM_JOB, **body}
    return client.post("/v1/provenance-records", json=payload, headers=_auth(key))


def test_s1_every_operation_requires_a_valid_key(setup) -> None:
    client, _, _ = setup
    record_id = _create(client).json()["record_id"]
    calls = [
        ("post", "/v1/provenance-records", {"provider": "ibm", "external_job_id": IBM_JOB}),
        ("get", f"/v1/jobs/{record_id}/provenance", None),
        ("get", f"/v1/jobs/{record_id}/provenance/versions", None),
        ("post", f"/v1/jobs/{record_id}/provenance/refresh", None),
    ]
    for headers in ({}, {"Authorization": "Bearer wrong-key"}, {"Authorization": "Basic x"}):
        for method, path, body in calls:
            response = client.request(method.upper(), path, json=body, headers=headers)
            assert response.status_code == 401, (method, path, headers)
            assert response.headers["www-authenticate"] == "Bearer"
            assert response.headers["content-type"] == "application/problem+json"
    assert client.get("/v1/openapi.json").status_code == 200


def test_s2_read_only_key_cannot_write(setup) -> None:
    client, _, _ = setup
    record_id = _create(client).json()["record_id"]
    assert _create(client, key="a_ro").status_code == 403
    refresh = client.post(f"/v1/jobs/{record_id}/provenance/refresh", headers=_auth("a_ro"))
    assert refresh.status_code == 403
    assert client.get(f"/v1/jobs/{record_id}/provenance", headers=_auth("a_ro")).status_code == 200


def test_s3_tenants_cannot_see_each_others_records(setup) -> None:
    client, _, _ = setup
    record_a = _create(client).json()["record_id"]
    for method, suffix in (("get", ""), ("get", "/versions"), ("post", "/refresh")):
        response = getattr(client, method)(
            f"/v1/jobs/{record_a}/provenance{suffix}", headers=_auth("b_rw")
        )
        assert response.status_code == 404
    created_b = _create(client, key="b_rw")
    assert created_b.status_code == 201
    assert created_b.json()["record_id"] != record_a


def test_s4_a_tenant_cannot_write_into_another_scope(setup) -> None:
    client, _, _ = setup
    assert _create(client, scope="tenant-b").status_code == 403
    assert _create(client, scope="tenant-a").status_code == 201


def test_record_lifecycle_create_idempotent_refresh_and_versions(setup) -> None:
    client, _, _ = setup
    first = _create(client)
    assert (first.status_code, first.headers["provenance-record-version"]) == (201, "1")
    record_id = first.json()["record_id"]
    again = _create(client)
    assert (again.status_code, again.headers["provenance-record-version"]) == (200, "1")
    refreshed = client.post(f"/v1/jobs/{record_id}/provenance/refresh", headers=_auth("a_rw"))
    assert (refreshed.status_code, refreshed.headers["provenance-record-version"]) == (201, "2")
    versions = client.get(f"/v1/jobs/{record_id}/provenance/versions", headers=_auth("a_rw"))
    assert [v["version"] for v in versions.json()["versions"]] == [1, 2]
    v1 = client.get(f"/v1/jobs/{record_id}/provenance?version=1", headers=_auth("a_rw"))
    assert v1.json()["generated_at"] == first.json()["generated_at"]
    latest = client.get(f"/v1/jobs/{record_id}/provenance", headers=_auth("a_rw"))
    assert latest.headers["provenance-record-version"] == "2"
    bad = client.get(f"/v1/jobs/{record_id}/provenance?version=0", headers=_auth("a_rw"))
    assert bad.status_code == 400


def test_request_errors_are_problems(setup) -> None:
    client, _, _ = setup
    headers = {**_auth("a_rw"), "content-type": "application/json"}
    assert client.post("/v1/provenance-records", content="{", headers=headers).status_code == 400
    assert _create(client, unexpected=1).status_code == 422
    assert _create(client, provider="rigetti").status_code == 404


def test_job_the_provider_does_not_know_gives_a_partial_record(setup) -> None:
    client, _, _ = setup
    response = _create(client, external_job_id="no-such-job")
    assert response.status_code == 201
    record = response.json()
    assert record["job"]["status"] == "unknown"
    reasons = {e["path"]: e.get("reason") for e in record["evidence"]}
    assert reasons["/job/status"] == "not_found_by_provider"


def test_s5_to_s7_no_secret_in_responses_keys_file_or_database(setup) -> None:
    client, db, keys_file = setup
    responses = [
        _create(client),
        _create(client, provider="ionq", external_job_id="leaky-job"),
        _create(client, key="a_ro"),
        client.get("/v1/jobs/x/provenance", headers=_auth("b_rw")),
        client.get("/v1/jobs/x/provenance", headers={"Authorization": "Bearer nope"}),
        _create(client, unexpected=f"Bearer {KEYS['a_rw'][0]}"),
    ]
    secrets = [*ENV_SECRETS.values(), UPSTREAM_SECRET, *(key for key, _, _ in KEYS.values())]
    for response in responses:
        exposed = response.text + json.dumps(dict(response.headers))
        for secret in [*ENV_SECRETS.values(), UPSTREAM_SECRET]:
            assert secret not in exposed, response.request.url
    stored = db.read_bytes().decode("utf-8", "replace") + keys_file.read_text()
    for secret in secrets:
        assert secret not in stored
