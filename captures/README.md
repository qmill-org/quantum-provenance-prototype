# Held-out live captures

Responses retrieved from real provider services after the contract and
adapters were frozen and published as `v0.1.0` (2026-07-20, Zenodo
10.5281/zenodo.21451599). None of these responses was available when the
adapters were designed, so they test the design rather than confirm it.

## Method

1. `python -m qmill_quantum_provenance.live.capture <provider> <job-id>...`
   calls the live integration retrieval methods in the order the provenance
   adapters call them and writes, per job, `fixture.json` (replayable through
   `ReplayIntegrationAdapter`, including recorded upstream errors),
   `native.json` (the provider responses) and `manifest.json` (per-operation
   outcome and mapping notes).
2. Captures are sanitized before writing: secret-like keys redacted, AWS
   account identifiers replaced by `000000000000`, and submitted or compiled
   program text replaced by a SHA-256 digest and byte size.
3. `python -m qmill_quantum_provenance.live.validate captures` runs the
   unchanged `v0.1.0` adapters over every capture, validates each record
   against the contract, classifies the attribute inventory, and checks the
   record's claims against facts recorded independently in the capture.

## Amazon Braket (captured 2026-11-18)

Published captures are limited to jobs whose programs and results may be
public: purpose-run jobs from [`runs/ledger.jsonl`](../runs/ledger.jsonl) and
expired tasks of a publicly archived campaign. Jobs of unknown origin in the
same account are never captured into the repository.

| Capture | Device | Created | Upstream outcome |
|---|---|---|---|
| `04470467…`, `0669f519…`, `2b9bc60e…` | IonQ Forte-1, IQM Emerald, Rigetti Cepheus-1-108Q | 2026-08-14 … 08-18 | `GetQuantumTask` → `ResourceNotFoundException` |
| `c5f722a5…` (`e2-ionq-forte1-ghz5`) | IonQ Forte-1 (us-east-1) | 2026-11-18 | complete |
| `e4279728…`, `8110d507…` (`e2-rigetti-cepheus-*`) | Rigetti Cepheus-1-108Q (us-west-1) | 2026-11-18 | complete |
| `a55acc36…` (`e5-rigetti-cepheus-cancelled`) | Rigetti Cepheus-1-108Q (us-west-1) | 2026-11-18 | cancelled on purpose; no result |

Three IQM tasks of the same plan were rejected at submission with
`DeviceOfflineException` (IQM Garnet and Emerald were `OFFLINE`); the rejection
is recorded in the ledger.

The three tasks belong to the publicly archived realization-divergence
campaign (183 tasks, 14–18 August 2026; Zenodo 10.5281/zenodo.22471564).

Validation of the `v0.1.0` adapters:
[`braket-validation-v0.1.0-adapters.json`](braket-validation-v0.1.0-adapters.json).

### Findings

F1–F2 rest on the expired campaign tasks; F3–F7 on the purpose-run jobs of
2026-11-18 (F3–F6 were first seen on jobs of unknown origin in the same account,
which are not published, and were then reproduced on purpose-run jobs).

- **F1 Retention boundary (undocumented).** The 183 tasks of the 14–18 August
  2026 campaign are no longer returned by `GetQuantumTask` (92–96 days after
  creation); the oldest task still listed by `SearchQuantumTasks` was created
  2026-08-31 (79 days). The tasks' `results.json` objects remain in the
  customer's S3 bucket, so the result artifact outlives the control-plane job
  record. No retention period was found in the Braket developer guide.
- **F2 Expired job yields no record.** For the three expired tasks the `v0.1.0`
  service raises instead of returning a partial record, although the result
  artifact still exists. The contract has no way to express "job metadata
  discarded by the provider, result artifact retained".
- **F3 Probabilities presented as observed counts.** IonQ through Braket
  returns only `measurementProbabilities` (no per-shot `measurements`); counts
  are an SDK expansion `round(p · shots)`. The `v0.1.0` Braket adapter labels
  them `provider_supplied` observed counts. The direct-IonQ adapter handles the
  same distinction correctly; the Braket path did not, and the `v0.1.0`
  fixture could not reveal it.
- **F4 Submitted program retained but not mapped.** Braket retains the
  submitted program (`additionalMetadata.action.source`) for all four tasks;
  the Braket adapter emits no `submitted` artifact.
- **F5 Documented field present but empty.** For IonQ Forte-1
  `ionqMetadata.compiledProgram` is an empty string; Rigetti populates
  `rigettiMetadata.compiledProgram`. Field documentation does not imply field
  population.
- **F6 Characterization is current-at-retrieval only, with coarse or missing
  timestamps.** IonQ `standardized.updatedAt` is a date at midnight
  (`2026-11-18T00:00:00Z` for a job that ended 22:40 the same day; on an
  earlier, non-published IonQ job the snapshot was dated 48.6 days after the
  job), so day granularity cannot establish which state the job ran under.
  Rigetti (and IQM, on the non-published jobs) expose no characterization
  timestamp at all, only the service-document `service.updatedAt`, which the
  live integration deliberately does not treat as one; the association is
  therefore unverifiable.
- **F7 Characterization attached to a job that never ran.** For the cancelled
  task the `v0.1.0` record is schema-valid and correctly marks results
  unavailable, but still attaches a `current_at_retrieval` device
  characterization to an execution that did not take place.
