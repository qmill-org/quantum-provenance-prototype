# Reference HTTP service — scope and security test plan (WP-E6)

Addresses R1.6: the submitted artifact offered two in-process operations, no
HTTP deployment, persistence, authentication or refresh semantics, and no
security test despite §5.2.3. Written before the implementation.

## Scope (what is claimed)

A **reference** service: it shows that the contract can be served over HTTP
with persistence, authentication, tenant isolation and refresh, and it is
tested against the contract and for the security properties below. It is not
a production multi-tenant deployment: no TLS termination, key rotation,
request-rate limiting, audit log, encryption at rest or horizontal scaling.
Those remain deployment concerns (§5.2.3, adoption).

## Design

- **Contract first.** Request bodies are validated against the contract's own
  JSON Schemas (`CreateProvenanceRecordRequest`), responses are the records
  the in-process service assembles, and the service publishes the contract it
  implements at `GET /v1/openapi.json`. The contract is extended (CC-9):
  bearer API-key security; 401/403 responses; `POST
  /v1/jobs/{job_id}/provenance/refresh`; `GET /v1/jobs/{job_id}/provenance/versions`;
  `version` query on `GET /v1/jobs/{job_id}/provenance`; response header
  `Provenance-Record-Version`.
- **Persistence.** SQLite; every assembly is stored as a new version with its
  `generated_at` and `retrieved_at`; a refresh adds a version and never
  overwrites one, because the earlier record is itself provenance (what was
  retrievable when).
- **Retrieval.** A fresh adapter per request (live retrieval layers hold
  per-job state). Mode `live` uses server-side provider credentials from the
  environment, never from clients; mode `replay` serves the committed captures.
- **Authentication and tenancy.** `Authorization: Bearer <key>`. Keys are
  configured as SHA-256 hashes with a tenant and permissions (`read`,
  `write`); presented keys are hashed and compared in constant time. The
  tenant is the contract's `scope`, folded into the canonical job ID, so two
  tenants registering the same provider job get different records.

## Security properties and tests

| ID | Property | Test |
|---|---|---|
| S1 | Every operation except the published contract requires a valid key (401 otherwise, with `WWW-Authenticate`). | explicit tests; Schemathesis `ignored_auth` check |
| S2 | A read-only key cannot create or refresh (403). | explicit |
| S3 | Tenant isolation: another tenant's record, versions and refresh answer 404 (no existence leak); the same provider job registered by two tenants yields two records. | explicit |
| S4 | A tenant cannot write into another tenant's scope (403). | explicit |
| S5 | No secret in any response, including errors: provider credentials in the server environment, API keys, and credentials inside upstream error messages. | sentinel secrets planted in env, keys and injected provider errors; all responses scanned |
| S6 | API keys are stored only as hashes. | key file and database scanned for the plain keys |
| S7 | The database holds no provider credential or API key. | sentinel scan of the SQLite file |
| S8 | Every response conforms to the contract and no request causes a server error. | Schemathesis property-based run over all operations |

Results are recorded below, including any defect the tests find.

## Log

| Date | Change | Reason |
|---|---|---|
| 2026-11-20 | Plan committed. | — |
