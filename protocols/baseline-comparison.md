# Baseline comparison protocol (WP-E4)

Addresses R2.2 (explicit baseline), R1.4 (compare correctness, not effort) and
R1.2 (self-confirming evaluation). Committed **before** the baseline, the
oracle and the record readers are implemented; changes after this commit are
logged at the end with their reason.

## Question

Given the same provider data, does a record produced under the evidence-aware
contract let a consumer answer provenance questions **correctly** more often,
and **mislead** less often, than a flat common-field record?

Effort (lines of code, development time) is not measured (R1.4).

## Arms

| Arm | What | Code |
|---|---|---|
| **B** — flat baseline | The QProv-aligned attribute set of Figure 2 as flat fields, without evidence, association, missingness or producer qualifiers. Each field is filled from the integration seam with the most direct accessor, the way a developer using the provider SDK's default accessors would. It is not a reimplementation of QProv. | `comparison/baseline.py` |
| **V1** — as submitted | `v0.1.0` adapters and contract (tag `v0.1.0`), unchanged. | git worktree of `v0.1.0` |
| **V2** — revised | `v0.2.0` adapters and contract as frozen by tag `baseline-freeze`. | this repository |

All arms read the **same** input: the capture's `fixture.json` through the
integration seam (`TaskSnapshot`, `TaskResult`, `DeviceDetails`). Recorded
provider errors (`upstream_errors`) are raised by the replay in every arm, so
an arm sees the failure the provider actually returned. V1 never supported
Quandela; its Quandela cells are scored "no record".

### Baseline fields (fixed)

`provider` (platform the job was retrieved from), `job_id`, `status` (provider
string, lower-cased), `created_at`, `ended_at`, `shots`, `qpu_name` (the target the job names),
`is_simulator`, `qubit_count`, `last_calibrated` and `calibration` (device
characterization as returned with the device details), `counts`
(`TaskResult.measurement_counts`), `compiled_circuit`
(`TaskResult.compiled_circuit`), `execution_time_ms`, `retrieved_at`. A field
the seam does not fill is `null`. If retrieving the job fails, the baseline
produces no record.

## Ground truth (oracle)

For each capture the oracle derives the true answer from the **provider's raw
responses** (`native.json`), the capture manifest written at retrieval time,
and the application's run ledger (`runs/ledger*.jsonl`, for what the
application requested). The oracle does not call any arm's mapping code. A
question the oracle cannot answer for a capture is not applicable there.

## Questions

A **reader** per arm answers each question from the record alone, using only
the documented meaning of that arm's fields (baseline: field names; V1/V2:
the contract's descriptions, evidence and association states). Readers do not
parse identifiers or consult provider documentation.

Targeted questions (derived from findings F1–F14, which is why the hold-out
set below matters):

| ID | Question | Finding |
|---|---|---|
| Q1 | What kind of result did the provider return: observed counts, probabilities only, or values derived by client software? | F3, F11, F14 |
| Q2 | Who produced the program presented as compiled or executed: provider or application? | F8 |
| Q3 | How does the device characterization relate in time to the execution: matched to it, taken after the job ended, or untimed? | F6, F7 |
| Q4 | Who operates the hardware, as distinct from the platform? | R1 (Table 9) |
| Q5 | When results are absent, why: job did not run, not yet available, or job no longer retrievable? | F2, F7 |
| Q6 | How many shots did the application request? | F11, F13 |
| Q7 | How many shots were executed? | F14 |
| Q8 | Which batch or session did the job run in? | F10 |
| Q9 | Why did a failed job fail? | — |
| Q10 | Which noise model produced a simulator result? | F13 |

Neutral questions (no qualifier needed; included so that the comparison does
not only test what V2 fixed):

| ID | Question |
|---|---|
| N1 | Which device ran the job? |
| N2 | When was the job created, and when did it end? |
| N3 | How many qubits does the device have? |

Record existence (Q0): did the arm produce a record at all?

Added after the freeze (see log; reported separately, not in the frozen
totals):

| ID | Question | Ground truth |
|---|---|---|
| Q11 | Do the recorded outcome counts equal the provider's raw per-shot data, outcome by outcome? | Braket `measurements` tallied (gate: bit strings; analog: the Braket SDK's documented `e`/`r`/`g` site convention, successful shots only); Quandela raw `counts`. IBM raw samples are not stored in the captures: not applicable. |

## Scoring

Each applicable (capture, question) pair is scored for each arm:

- **correct** — the reader's answer equals the oracle's;
- **misleading** — the record states, or by its field definitions implies, a
  wrong answer;
- **undeterminable** — the record does not allow an answer (field absent, or
  present without the information needed);
- **no record** — the arm produced no record.

Primary outcome: misleading answers per arm. Secondary: correct and
undeterminable answers. Reported per question and per capture set, as counts
(no significance testing; the unit is a real job, and there are few).

## Capture sets

- **Development set** — the 21 captures existing at this commit. V2 was
  revised on these captures, so V2's results here are expected and are
  reported as such, not as evidence.
- **Hold-out set** — captures taken after tag `baseline-freeze`: the jobs
  still pending at this commit (AQT Ibex-Q1, QuEra Aquila ×2, Quandela Belenos
  QPU) and any later purpose-run jobs. Neither the adapters nor the readers or
  the oracle are changed after the freeze without a log entry here; if they
  are, hold-out results are reported both before and after the change.

### Hold-out job set H1 (registered 2026-11-20, before submission)

Free tiers only. Chosen to differ from the development jobs and to reach code
paths no development capture exercised:

| Key | Platform | What is new |
|---|---|---|
| `h1-ibm-sampler-ghz5-twirled` | IBM `ibm_aachen`, SamplerV2 | gate and measurement twirling: executed shots differ from requested for a Sampler |
| `h1-ibm-estimator-ghz5-r0` | IBM `ibm_aachen`, EstimatorV2 | resilience level 0, five-qubit observable `IIIZZ` |
| `h1-ionq-noisy-aria1-bell2` | IonQ simulator | noise model `aria-1`, fixed seed 42 |
| `h1-ionq-multicircuit` | IonQ simulator | `ionq.multi-circuit.v1` (Bell + GHZ-5): parent job with child jobs |
| `h1-quandela-sim-belenos-interferometer6` | Quandela `sim:belenos` | three photons, six modes |

Plus the jobs pending at the freeze (AQT Ibex-Q1, Quandela Belenos QPU).

### 2026-11-20: H1 IonQ jobs (aria-1 noisy Bell; multi-circuit Bell + GHZ-5)

Scored as pre-registered (cumulative hold-out, with Aquila): frozen questions
B 26/2/9/0, V1 24/0/4/9, V2 35/0/2/0, V2f 35/0/2/0.

**Unscored failure (F16).** The multi-circuit job completed, but the IonQ
retrieval layer requests `/results/probabilities`, while IonQ advertises a
different location for multi-circuit jobs in the job itself
(`results.probabilities.url` → `.../results/probabilities/aggregated`, keyed by
child job). The request returns 404, and V2 records the results as
unavailable with reason `not_found_by_provider`, which is false. The oracle
cannot score this: it reads the raw data the same retrieval layer captured,
so a retrieval miss makes the question not applicable instead of wrong. This
is a limit of an oracle built on the capture layer. V2 does carry the two
child job identifiers (`job.relations.child_job_ids`, provider-supplied);
B and V1 cannot.

After the fix (retrieval layer follows the advertised location; the parent
re-captured and its two child jobs captured as jobs in their own right):
cumulative hold-out, frozen questions B 38/2/17/0, V1 43/0/14/0, V2 55/0/2/0,
V2f 55/0/2/0. Unscored but decisive for R1.4: given the same, now complete,
input, the parent's per-child results are new to the older adapters. V1
reports `upstream_request_failed` (false); V2f, frozen after AC-6, reports
`unrecognized_result_format` (true: the adapter does not understand the
result); V2 states that the results belong to the child jobs, and each child
record carries `parent_job_id` and its own distribution.

## Threats stated in advance

- The baseline, the readers and the questions are designed by the authors of
  V2; the targeted questions come from defects V2 was revised to fix. The
  neutral questions and the hold-out set are the counterweights.
- The baseline's reader takes field names at face value (e.g. `provider`
  read as the operator, `counts` as observed counts). A sensitivity reading in
  which a consumer parses device identifiers is reported for Q4.

## Results — development set (21 captures, freeze `824f512`)

Counts of (capture, question) pairs: correct / misleading / undeterminable /
no record. Full detail: `artifact/baseline-comparison.json`.

| Question | B | V1 | V2 |
|---|---|---|---|
| Q0 record produced | 18/0/0/3 | 16/0/0/5 | 21/0/0/0 |
| Q1 result kind | 11/1/3/0 | 11/2/0/2 | 15/0/0/0 |
| Q2 program producer | 8/6/1/0 | 6/6/1/2 | 15/0/0/0 |
| Q3 characterization timing | 13/0/0/0 | 13/0/0/0 | 13/0/0/0 |
| Q4 hardware operator | 12/6/0/0 | 16/0/0/2 | 18/0/0/0 |
| Q5 why results are absent | 3/0/0/3 | 3/0/0/3 | 6/0/0/0 |
| Q6 requested shots | 14/2/2/0 | 14/0/2/2 | 14/0/4/0 |
| Q7 executed shots | 11/1/1/0 | 9/1/1/2 | 13/0/0/0 |
| Q8 batch/session | 0/0/16/0 | 0/0/16/0 | 16/0/0/0 |
| Q9 failure reason | 0/0/1/0 | 0/0/1/0 | 1/0/0/0 |
| Q10 noise model | 0/0/3/0 | 0/0/3/0 | 3/0/0/0 |
| N1 device | 18/0/0/0 | 16/0/0/2 | 18/0/0/0 |
| N2 created/ended | 16/0/2/0 | 16/0/0/2 | 18/0/0/0 |
| N3 qubit count | 16/0/0/0 | 16/0/0/0 | 16/0/0/0 |
| **Total** | **140/16/29/6** | **136/9/24/22** | **187/0/4/0** |

Reading notes:

- V2 was revised on these captures, so its zero misleading answers here are
  expected, not evidence; the hold-out set is the test.
- Misleading answers in B: probabilities shown as counts (Q1, Braket–IonQ);
  application-compiled IBM circuits read as the provider's (Q2, 6); the
  platform read as the hardware operator (Q4, 6 Braket jobs; 0 under the
  cautious reading); photon detections read as requested shots (Q6, Quandela
  ×2); executor shots for the Estimator (Q7). V1 shares Q1, Q2 and Q7, and
  adds an Estimator result reported as a failed retrieval.
- No arm misleads on Q3: once the seam supplies a characterization timestamp,
  a consumer can compare it with the job's times. The association states add
  nothing measurable here; the value is the timestamp itself (and, for the
  untimed Braket devices, its explicit absence).
- V2's four undeterminable answers are requested shots that the provider does
  not record (Quandela, IonQ simulator); the application can supply them.
- All arms share the integration seam, so seam fixes made during this work
  (IBM properties as of job creation, IBM requested shots) benefit B and V1
  too: the comparison isolates the mapping, and understates the difference
  to a baseline written directly against provider SDKs.
- Neutral questions: B and V2 tie on N1 and N3; B leaves the Quandela end time
  undeterminable (N2) because it does not derive it.

## Results — hold-out set

### 2026-11-20: QuEra Aquila ×2 (analog Hamiltonian simulation via Braket)

Captured after the freeze (`4852fae4`, `808c58a0`). Scored as pre-registered:

| Arm | correct / misleading / undeterminable / no record |
|---|---|
| B | 14 / 2 / 2 / 0 (misleading: Q4 operator ×2) |
| V1 | 16 / 0 / 2 / 0 |
| V2 | 18 / 0 / 0 / 0 |

**Unscored failure found on the hold-out set (F15).** In every arm the
result is `measurement_counts = {"shotMetadatashotResult": 100}`: the shared
Braket retrieval layer tallies a shot by joining its elements, assuming a list
of bits, and an AHS shot is an object (`shotMetadata`, `shotResult` with pre-
and post-sequence site occupations). V2 labels these counts
`provider_supplied` with `outcome_basis: bitstring`; no drift warning fires
and the live validator reports no finding, because a result was produced.
The pre-registered Q1 asks only which kind of result the provider returned
(observed per-shot measurements: correct in all arms), not whether the
recorded outcomes are correct, so the scored table does not show the failure.
This is reported as a limitation of the question set, not re-scored.

Post-freeze Q11 (outcome content), before any fix: B 0/2/0/0, V1 0/2/0/0,
V2 0/2/0/0 (misleading in every arm). Development set: B 6/0/0/0, V1 4/0/0/2,
V2 6/0/0/0.

After the fix (retrieval layer and Braket adapter, `F15` below; the two jobs
re-captured, the pre-fix captures remain at `b8014a8`), with arm V2f = V2 as
frozen at `baseline-freeze`:

| Arm | frozen questions c/m/u/n | Q11 |
|---|---|---|
| B | 14 / 2 / 2 / 0 | 2 / 0 / 0 / 0 |
| V1 | 16 / 0 / 2 / 0 | 2 / 0 / 0 / 0 |
| V2 (fixed) | 18 / 0 / 0 / 0 | 2 / 0 / 0 / 0 |
| V2f (frozen) | 18 / 0 / 0 / 0 | 2 / 0 / 0 / 0 |

Reading notes: the corruption was in the shared retrieval layer, so once it
is fixed every arm records the right outcomes. What the adapter adds is the
meaning: V2 labels the outcomes `site_occupation` with `derived` evidence
naming the convention, whereas V2f (and V1, B) present the same strings as
bitstrings. No question scores the basis (unscored). Under the frozen Q1
reader the fixed V2 scored 2 misleading (derived counts read as client-
computed values); the reader was corrected to the contract's definition (log),
which also shows that the evidence state alone does not tell a machine reader
whether derived values are relabelled observations or computed estimates
(input to R2.4).

## Log

| Date | Change | Reason |
|---|---|---|
| 2026-11-20 | Protocol committed. | — |
| 2026-11-20 | Baseline `qpu_name` taken from the target the job names instead of the device's display name. | First run scored correct display names ("Forte 1") as misleading against device identifiers; the job's own target field is the more direct accessor. Before freeze; no hold-out data. |
| 2026-11-20 | V1 harness: a recorded provider error is raised with its recorded class when `v0.1.0` defines it (as the current replay does), not as a generic error. | The generic error made `v0.1.0` drop three records it produces in the frozen `v0.1.0` report (cancelled/failed jobs). Harness only. Before freeze. |
| 2026-11-20 | Hold-out results for the two Aquila jobs recorded as scored; F15 recorded as an unscored failure. No change to adapters, oracle or readers yet. | Hold-out discipline: results are reported before any fix. |
| 2026-11-20 | Q11 added (outcome content), scored separately from the frozen totals. | F15 showed that the frozen Q1 checks only the kind of result, so a corrupted result scores as correct. Added after hold-out data were seen; reported as post-freeze. |
| 2026-11-20 | F15 fixed: the Braket retrieval layer tallies analog shots with the Braket SDK's documented site convention (successful shots only) and no longer tallies shot layouts it does not recognize (they now yield no counts and an `unrecognized_result_format` warning); the Braket adapter labels analog outcomes `site_occupation` with `derived` evidence. Aquila jobs re-captured. | Post-freeze fix of a hold-out failure; results reported before (above, `63ce25f`) and after. |
| 2026-11-20 | Arm V2f added: V2 as frozen at `baseline-freeze`, run from a worktree, so every hold-out capture is scored with and without post-freeze changes. | Hold-out discipline after the first post-freeze change. |
| 2026-11-20 | Q1 reader: `measurement_counts` always read as observed counts (the contract's definition); previously counts with `derived` evidence were read as client-computed. | The frozen rule contradicted the contract text the protocol requires readers to use; it first mattered for the analog counts. Development results unchanged. |
| 2026-11-20 | Hold-out job set H1 registered (above) before submission. | Hold-out set otherwise only Aquila, AQT and Belenos. |
| 2026-11-20 | H1 IonQ results recorded as scored; F16 recorded as unscored, with the oracle limitation. | Results reported before any fix. |
| 2026-11-20 | F16 fixed: the IonQ retrieval layer follows `results.probabilities.url`; a multi-circuit parent records results as not applicable, pointing to its child jobs (shared rule: an adapter's own not-applicable explanation is not overwritten or warned about). Parent re-captured; child jobs `06b000ed-feec…`, `06b000ed-feed…` captured. | Post-freeze fix of a hold-out failure; before (`b91d015`) and after reported. |
