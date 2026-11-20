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

Validation reports, one per adapter version, over the same captures:

- [`validation-v0.1.0-adapters.json`](validation-v0.1.0-adapters.json) — the
  published `v0.1.0` adapters (Braket, IBM, IonQ). Frozen: not regenerated
  after the adapters changed.
- [`validation-v0.2.0-dev-adapters.json`](validation-v0.2.0-dev-adapters.json)
  — the development adapters (all providers, including Quandela).

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

## IBM Quantum (captured 2026-11-19)

Seven purpose-run jobs on `ibm_aachen` (Heron r3, eu-de), submitted with
[`scripts/run_ibm_jobs.py`](../scripts/run_ibm_jobs.py) and listed with their
application-captured context in [`runs/ledger-ibm.jsonl`](../runs/ledger-ibm.jsonl):
Sampler Bell-2 and GHZ-5, a Batch of three Sampler Bell-2 jobs compiled at
optimization levels 0, 1 and 3, an Estimator ⟨ZZ⟩ job, and one Sampler job
cancelled on purpose. Circuits were compiled by the application (Qiskit
preset pass manager, `seed_transpiler=1234`); the Bell circuit landed on
qubits [0, 1], [86, 87] or [87, 88] depending on the optimization level, which
only the application context records.

The program files use the Braket OpenQASM 3 dialect (built-in `h` and `cnot`,
no `stdgates.inc`); Qiskit rejects them as written (`gate 'h' is not
defined`). The run script converts them (add the include, rename `cnot` to
`cx`) and records both digests: the same "OpenQASM 3" source is not portable
across providers, which is why the model separates `source` and `submitted`
artifacts.

All seven `v0.1.0` records are schema-valid. Characterization was retrieved
as of job creation (`properties(datetime=…)`); the snapshot preceded each job
by 0.2 h, so IBM supports a timestamp-matched association that the adapter
labels only `nearest_available`.

### Findings

- **F8 Application-compiled program attributed to the provider.** With
  Sampler/Estimator V2 the application compiles the ISA circuit and submits
  it; IBM returns it with the job. The `v0.1.0` record labels it a `compiled`
  artifact with `provider_passthrough` evidence and no producer, and emits no
  `submitted` artifact (6 of 6 completed jobs).
- **F9 Interface drift during the study.** With `qiskit-ibm-runtime` 0.52 job
  inputs follow `schema_version` `v2.0` (`quantum_program` with
  `CircuitItem`/`SamplexItem`), not the PUB list assessed in July 2026; both
  Sampler and Estimator jobs record `primitive_id = "executor"`, so the
  provider-side job no longer says which primitive was used.
- **F10 Multi-job lineage is lost.** The three Batch jobs share the provider's
  batch identifier (`session_id`), but the `v0.1.0` contract has no session,
  batch or parent field, so the relation disappears from the records.
- **F11 Expectation-value results reported as a failed retrieval.** The
  Estimator job returns expectation values and no counts; the `v0.1.0` record
  says `results.available = false` with reason `upstream_request_failed`, and
  reports `shots = 64` (shots per twirling randomization recorded by the
  executor) instead of the 1000 the application requested.
- **F14 Primitive results are computed by the client, not the provider.**
  With `qiskit-ibm-runtime` 0.52 the server runs an executor program and
  returns per-shot samples (`_meas`, `measurement_flips._meas`) together with
  the caller's primitive options as pass-through data. The Estimator's
  expectation values and standard errors are computed locally by the SDK's
  `ClientSideEstimatorDecoder` (here with measurement-error mitigation,
  resilience level 1). The job executed 2 items × 16 randomizations × 64 shots
  = 2048 shots for a request of 1000. A record must therefore label the
  expectation values as derived by named client software, and keep requested
  and executed shots apart.

## IonQ direct API v0.4 (captured 2026-11-19)

Three purpose-run jobs on the free IonQ cloud simulator, submitted with
[`scripts/run_ionq_jobs.py`](../scripts/run_ionq_jobs.py)
([`runs/ledger-ionq.jsonl`](../runs/ledger-ionq.jsonl)): Bell-2 on the ideal
simulator, GHZ-5 with the `forte-1` noise model, and a job with a deliberately
invalid gate. The application converts the shared OpenQASM programs to
`ionq.circuit.v1` JSON before submission. Characterization retrieval was also
exercised read-only against `qpu.forte-1`.

The direct path keeps result semantics right where the Braket path does not
(F3): probabilities are `provider_supplied`, estimated counts `derived`, and
observed counts `not_applicable`. IonQ retains provider-compiled circuits as
job artifacts (`ionq.native.v1`, `ionq.qasm3.v1`), and its v0.4 job resource
carries `session_id`, `parent_job_id` and `child_job_ids` — native multi-job
lineage (cf. F10). The invalid gate was accepted (HTTP 201), stayed
`submitted` for minutes, then failed with `CompilationError`; the record has
status `failed` and the reason only inside a free-text warning.

### Findings

- **F12 Silent degradation after a field rename.** API v0.4 reports
  `execution_duration_ms`; the `v0.1.0` adapter reads the v0.3 name
  `execution_time_ms` and reports the run duration as `unavailable` without
  any warning. The record stays schema-valid, so the break is visible only by
  comparing against the provider response. Likewise, v0.4 jobs no longer carry
  the `characterization_id` the `v0.1.0` fixture used for the
  `provider_linked` association; the backend exposes only its current
  characterization, and history must be matched by date (`end=` query, daily
  snapshots dated 00:00 UTC).
- **F13 Simulation provenance has no place in the record.** The noisy job's
  noise model (`forte-1`) and seed are recorded by IonQ but the contract has
  no field for them, so the record shows a plain `simulator` run; the ideal
  simulator job records `shots = null` although 1000 were requested.
  (Addressed in `v0.2.0`: noise model and seed in
  `extensions["simulation.ionq"]`; requested shots application-captured.)
