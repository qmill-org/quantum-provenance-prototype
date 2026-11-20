# Changelog

## 0.2.0 — unreleased (revision of the QIP submission)

Responds to the reviews of the paper. `v0.1.0` (Zenodo
10.5281/zenodo.21451599) is the artifact as submitted and is unchanged;
every capture taken after its tag is held-out data for it.

### Live evidence

- Live retrieval layers for Amazon Braket, IBM Quantum, IonQ (API v0.4) and
  Quandela (`live/`), with capture, sanitization (secrets, account identifiers,
  IBM IAM principals, credentials in free text, program text replaced by
  digests) and validation tools.
- 30 sanitized captures of real jobs (`captures/`), run on purpose from the
  run ledgers (`runs/`): IonQ Forte-1, Rigetti Cepheus, IQM Garnet, AQT Ibex-Q1
  and QuEra Aquila (analog) through Braket; IBM `ibm_aachen` (Sampler,
  Estimator, Batch, twirling, cancellation); IonQ simulators (noise models,
  multi-circuit with child jobs, a failed job); Quandela `sim:belenos`; three
  expired Braket tasks. Findings F1–F18 in `captures/README.md`.
- Quandela as a new provider, integrated under a pre-registered protocol
  (`protocols/new-provider-quandela.md`).

### Contract (all changes additive; `0.1.0-prototype` records remain valid)

- CC-1 `extensions` (namespaced `<paradigm>.<provider>`); CC-2
  `results.outcome_basis` (bitstring, Fock state, site occupation, other);
  CC-3 `Artifact.producer`; CC-4 characterization `delta_seconds`,
  `timestamp_source`, `timestamp_granularity`; CC-5 `job.relations`
  (session, batch, parent/child, application experiment) and `job.failure`;
  CC-6 reason `not_found_by_provider`; CC-7 `execution.executed_shots` and
  request `requested_shots`; CC-8 `Evidence.artifact_role`; CC-9 HTTP
  security (bearer API keys), refresh, versions and links.
- Attribute inventory 0.2.0: result applicability decided per record;
  `job.relations`, `job.failure`, `execution.executed_shots` added.

### Adapters

- AC-1 result representations kept as returned (probabilities are never
  presented as counts); AC-2 artifact producers; AC-3 characterization timing;
  AC-4 job relations and failures; AC-5 partial records on upstream failure;
  AC-6 interface-drift detection; AC-7 requested vs executed shots and
  expectation-value results; AC-8 simulation extension; AC-9 status
  vocabularies of all four providers.
- Fixes from the hold-out set and failure injection: analog (AHS) results
  (F15), IonQ multi-circuit results (F16), twirled-Sampler shots (F17),
  transport faults, malformed provider values, failure reasons, credentials
  in provider error text (F18).

### Experiments (pre-registered; results before and after fixes)

- Baseline comparison (`protocols/baseline-comparison.md`,
  `artifact/baseline-comparison.json`): flat baseline, `v0.1.0` and `v0.2.0`
  on 21 development and 9 hold-out captures.
- Failure injection (`protocols/failure-injection.md`,
  `artifact/failure-injection.json`): transport faults, 55 seam faults on six
  real captures, and a real interface change.
- Live validation of every capture (`captures/validation-v0.2.0-adapters.json`;
  the `v0.1.0` report is kept frozen).
- The evaluation report (`artifact/evaluation-results.json`) and example
  records are computed from real captures, one per provider path, with the
  application context recorded at submission. The `v0.1.0` schema-change,
  field-rename and no-calibration experiments are removed (superseded).

### Service

- Reference HTTP service (`server/`, `protocols/http-service.md`): FastAPI,
  SQLite with versioned records, refresh, hashed API keys with tenant
  isolation; security tests S1–S8 and Schemathesis conformance.

### Supplementary

- Evidence ledgers: dated errata for versions at the July 2026 cutoff and the
  QuEra "authenticated" wording.

## 0.1.0 — 2026-07-20

Artifact as submitted with the paper: in-process service, Braket, IBM and IonQ
adapters over synthetic fixtures.
