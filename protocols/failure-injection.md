# Failure-injection protocol (WP-E5)

Addresses R2.5 (broaden the partial-record experiment: more failure modes,
several missing sections, upstream failures, more providers) and R1.4 (the
submitted experiments showed graceful failure, not adaptation). Committed
**before** the harness is implemented; later changes are logged at the end.

This is a conformance experiment, not a hold-out test: the cases are designed
by the authors of the adapters, with knowledge of them. Its value is breadth
and the explicit expected outcome per case, stated here in advance.

## Question

When retrieval fails or provider data are missing or malformed, does the
system (a) keep producing a schema-valid record, (b) report every affected
attribute as missing with the right reason instead of a fabricated value,
(c) leave unaffected attributes unchanged, and (d) never crash?

## Stage A — transport faults at the retrieval layer

For each live retrieval layer (Braket via boto3, IBM via qiskit-ibm-runtime,
IonQ via httpx, Quandela via Perceval), a fake client raises, for each
retrieval operation (`get_status`, `get_result`, `get_device_details`), the
exception **that client library actually raises** for:

| Fault | Expected integration error |
|---|---|
| timeout | `ProviderIntegrationError` |
| HTTP 401, 403 | `AccessDeniedError` |
| HTTP 404 | `JobNotFoundError` |
| HTTP 429 | `ThrottledError` |
| HTTP 500, 503 | `ProviderIntegrationError` |
| malformed JSON body | `ProviderIntegrationError` |
| truncated JSON body | `ProviderIntegrationError` |

Outcomes per cell: **as expected**; **other integration error** (caught by
the adapters, but the reason will be wrong); **escaped** (a non-integration
exception leaves the layer: in the service this means no record). Malformed
and truncated bodies apply where the layer parses a body itself. `v0.1.0`
had no live retrieval layer; Stage A covers `v0.2.0` only.

## Stage B — faults at the integration seam, through adapters and service

Base records: one completed real capture per provider path —
Braket/Rigetti `8110d507`, Braket/IonQ `c5f722a5`, Braket/QuEra (analog)
`808c58a0`, IBM Sampler `dbvb21ep`, IonQ simulator `01a1f2eb-d155`,
Quandela `5614c93a`.

Fault families, applied to each base as a fixture mutation:

1. **Upstream errors**: `JobNotFoundError`, `AccessDeniedError`,
   `ThrottledError`, `ProviderIntegrationError` × operation (`get_status`,
   `get_result`, `get_device_details`): 12 cases.
2. **Missing sections** (provider answered, part absent): device
   characterization; device properties; result payload; compiled program;
   measurement counts; job timestamps; job shots; job metadata. All 8 singly,
   all 28 pairs, and all 8 together: 37 cases.
3. **Malformed values**: shots as a string; unparsable creation time;
   non-integer count; non-numeric characterization metric; metadata timestamps
   not an object; result payload a list: 6 cases.

Arms: **V1** (`v0.1.0`, git worktree; no Quandela adapter) and **V2**
(current). Recorded errors are raised in both, by class name where the arm's
integration module defines it, else as its generic integration error.

### Affected attributes (fixed)

| Fault | Affected inventory attributes |
|---|---|
| error at `get_status` | all |
| error at `get_device_details`; missing characterization | `device.qubit_count`, `characterization` (+ `device.type` for the error) |
| missing device properties | `device.qubit_count` |
| error at `get_result`; missing result payload | `results.*`, `artifact.compiled`, `execution.executed_shots` |
| missing compiled program | `artifact.compiled` |
| missing measurement counts | `results.*` |
| missing timestamps | `job.created_at`, `job.ended_at`, `execution.*_duration_ms` |
| missing shots | `job.shots` |
| missing metadata | attributes the adapter reads from metadata (reported, not scored) |
| malformed value | the attribute holding it |

### Expected reason for an upstream error

| Error | `reason` on affected attributes |
|---|---|
| `JobNotFoundError` | `not_found_by_provider` |
| `AccessDeniedError` | `authentication_scope_insufficient` |
| `ThrottledError`, `ProviderIntegrationError` | `upstream_request_failed` |

### Measures per (arm, base, case)

- **M1 crash**: an exception leaves `create_record`.
- **M2 record**: a record is produced; **M3** it validates against the arm's
  own contract.
- **M4 honest**: no affected attribute is reported with a value as
  `provider_supplied`, `provider_passthrough`, `aggregator_normalized` or
  `derived` unless that value equals the base record's (a value that survives
  from another source is not fabricated).
- **M5 reason**: for upstream errors, affected attributes reported
  `unavailable` carry the expected reason.
- **M6 isolation**: every unaffected attribute keeps the base record's
  evidence status and value.
- **M7 signal**: the record carries a warning for the fault.

Missing-metadata cases are reported for M1–M3 and M7 only.

## Stage C — real interface changes replayed

Instead of the submitted synthetic IBM rename, replay changes that happened
in provider interfaces during the study, as pairs of real responses (before,
after):

| Change | Before | After |
|---|---|---|
| IonQ API v0.3 → v0.4 (`execution_time_ms` → `execution_duration_ms`; `characterization_id` removed from jobs) | `v0.1.0` IonQ fixture (v0.3 shape) | live v0.4 capture |
| qiskit-ibm-runtime: PUB-list inputs → `schema_version` v2.0 `QuantumProgram`; `primitive_id` → `executor` | `v0.1.0` IBM fixture | live capture |

Per changed attribute and arm: **delivered** (value present with correct
evidence), **silently lost** (unavailable, no warning), **flagged** (a drift
warning), or **wrong**.

## Reporting

Counts per stage, family, arm and measure; every non-expected cell listed.
Results in `artifact/failure-injection.json`. No effort measures.

## Results before fixes (2026-11-20, `artifact/failure-injection.json` at this commit)

### Stage A — transport faults (108 cells; V2 retrieval layers)

| Provider | as expected | other integration error | escaped | n/a |
|---|---|---|---|---|
| Braket | 17 | 1 | 7 | 2 |
| IBM | 24 | 3 | 0 | 0 |
| IonQ | 18 | 0 | 9 | 0 |
| Quandela | 25 | 0 | 2 | 0 |

Escaped (no record would be produced): Braket timeouts crash the error
translator itself (botocore timeout exceptions have `response = None`) and
malformed or truncated S3 `results.json` and `deviceCapabilities` raise
`JSONDecodeError`; IonQ lets `httpx` timeouts and `JSONDecodeError` through
on every operation; Quandela's own parse of the inner results document
escapes. Wrong error: IBM rate limiting (HTTP 429) is not recognized (generic
error); S3 `InvalidAccessKeyId` is not recognized as an access failure.

### Stage B — seam faults (cases failing each measure)

| Arm | Family | cases | crash | invalid | fabricated | wrong reason | not isolated | no warning |
|---|---|---|---|---|---|---|---|---|
| V1 | upstream error | 60 | 40 | 0 | 0 | 20 | 0 | 0 |
| V1 | missing sections | 185 | 0 | 0 | 0 | 0 | 0 | 185 |
| V1 | malformed | 19 | 2 | 8 | 11 | 0 | 0 | 17 |
| V2 | upstream error | 72 | 0 | 0 | 0 | 72 | 0 | 0 |
| V2 | missing sections | 222 | 0 | 0 | 6 | 0 | 6 | 129 |
| V2 | malformed | 23 | 6 | 5 | 9 | 0 | 0 | 16 |

(Not applicable: 13 malformed cases where the base has no such value.)

V1: every status or result retrieval error leaves no record (40); device
errors give records with a generic reason. V2 never crashes on upstream
errors, but:

- **wrong reasons** (all 72): a failed status retrieval states reasons at
  three paths only (456 attribute-level misses); a failed device or result
  retrieval is reported as `not_exposed_by_provider` for `device.type`,
  `device.qubit_count`, `characterization` and `execution.executed_shots`
  (the provider does expose them; retrieval failed); an absent artifact role
  (`artifact.compiled`) cannot carry a reason at all in the contract;
- **fabrication** (6): with the Braket result payload missing, the Braket-IonQ
  record falls back to the SDK's counts expanded from probabilities and labels
  them `provider_supplied` (F3 again);
- **malformed values** (6 crashes, 9 passed through as provider-supplied,
  5 schema-invalid records): string shots and counts, a non-numeric
  characterization metric and an unparsable Quandela time are not checked.
- **not isolated** (6): Quandela executed shots and requested shots share one
  provider field, so removing it affects both (a coupling, not an error).
- **no warning** for 129 missing-section cases: a missing section is reported
  per attribute in the evidence, not as a warning. M7 was stated as a measure,
  not a criterion; reported as is.

### Stage C — real interface change (IonQ run duration)

| Response | V1 | V2 |
|---|---|---|
| v0.3 (`execution_time_ms`) | delivered | delivered |
| v0.4 (`execution_duration_ms`), real capture | silently lost | delivered |
| unknown future rename (control) | silently lost | flagged |

The IBM input-layout change (PUB list → v2.0) is absorbed by the retrieval
layer: requested shots are read from both layouts (4096 and 1000 in the
check).

## Log

| Date | Change | Reason |
|---|---|---|
| 2026-11-20 | Protocol committed. | — |
| 2026-11-20 | Harness: Braket Stage A fake used the masked placeholder account, which makes the layer call STS; replaced by an ordinary account id. | Harness error; no layer change. |
| 2026-11-20 | Harness: cases that remove metadata excluded from M4–M6 when metadata is one of several removed sections (the protocol's rule; the code applied it to the single case only). | Implementation did not follow the protocol. |
| 2026-11-20 | M6 compares evidence status only; an attribute the base record reports as `derived` may change when a source is removed (reported as a dependency, still checked for fabrication). | First run counted correct derived-value changes (e.g. Braket executed shots counted from the removed measurements) as isolation failures. |
| 2026-11-20 | M5 takes the reason at the attribute's evidence path or its nearest ancestor (e.g. `/results` for `results.*`). | A section-level reason applies to its attributes. |
| 2026-11-20 | "Unparsable creation time" is injected in the provider field the adapter parses itself (IBM `timestamps.created`, Quandela `creation_datetime`); the seam parses snapshot times itself. Not applicable to Braket and IonQ bases. | Implementation detail fixed before the first full run. |
| 2026-11-20 | Results before fixes recorded (above). | Reported before any fix. |
