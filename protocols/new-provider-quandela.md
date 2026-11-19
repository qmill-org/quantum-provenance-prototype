# Protocol — new-provider integration: Quandela Cloud (WP-E3)

Written and committed **before** the Quandela API was examined beyond the
public documentation used in the July 2026 comparative analysis. Deviations
from this protocol are recorded in the log at the end, with date and reason.

## Purpose

Test whether the `v0.1.0` common contract and extension mechanism accommodate
a provider and a computing paradigm they were not designed against:

- **R2.1** — a new-provider integration scenario for the adapter architecture;
- **R1.3** — a non-gate paradigm (photonic, linear-optical) backed by real
  execution.

Quandela was one of the 15 platforms in the documentation analysis, but no
Quandela adapter, fixture or mapping existed, and none influenced the
`v0.1.0` contract.

## Frozen baseline

Repository commit `6805da8` (branch `feat/live-retrieval`). The shared,
provider-independent files are unchanged since `v0.1.0` except a docstring in
`service.py`:

| File | SHA-256 (first 12) |
|---|---|
| `src/qmill_quantum_provenance/openapi.json` (contract) | `f0d9f32e64c9` |
| `src/qmill_quantum_provenance/models.py` | `981b8127565a` |
| `src/qmill_quantum_provenance/service.py` | `f0ee70357e7e` |
| `src/qmill_quantum_provenance/adapter.py` | `015dc018a1fc` |
| `src/qmill_quantum_provenance/registry.py` | `06da465c642a` |
| `src/qmill_quantum_provenance/contract.py` | `2e470e474ee8` |
| `src/qmill_quantum_provenance/redaction.py` | `469cf43ef9a3` |
| `artifact/attribute-inventory.json` | `d977cfeb87b1` |

## Procedure

1. **Read-only probe.** Inspect platforms, platform specifications and
   characterization data through the Quandela Cloud API with the project
   token. No jobs.
2. **Mapping table before code.** For every Quandela field relevant to the
   41-attribute coding rubric and the 21-attribute prototype inventory, decide
   the record location and evidence state: common core, namespaced
   `extensions`, or not representable. Commit the table before implementing.
3. **Implement** the live integration (`live/quandela.py`) and the provenance
   adapter (`adapters/quandela.py`) plus a registry entry. Shared files are
   not edited during this step (rule R-1).
4. **Purpose-run jobs.** A small photonic circuit (e.g. two-mode Hong–Ou–Mandel
   and a 4-mode interferometer) on the free simulator and, if a free QPU slot
   is available, on a Quandela QPU; recorded in a run ledger with
   application-captured context.
5. **Capture and validate** with the same tools as for Braket, IBM and IonQ.

## Rules

- **R-1 No silent core changes.** If the contract or shared code must change,
  stop, record the change, the reason and the attribute that forced it in the
  log below, then make it as a separate commit.
- **R-2 Inventory is fixed.** The 21-attribute inventory is not edited to fit
  Quandela; attributes that do not apply are classified by its existing
  applicability rules or reported as gaps.
- **R-3 Report what did not fit**, including concepts placed in
  `extensions` only because the core had no place for them.

## Measures

| ID | Measure | Source |
|---|---|---|
| M1 | Files changed outside the Quandela adapter and integration, each classified: contract change / shared-code change / extension use / bug fix | `git diff --stat 6805da8` |
| M2 | Rubric and inventory attributes mapped to the core, to `extensions`, or not representable | mapping table |
| M3 | Evidence states used, and attributes `unavailable` vs `not_applicable` | validation report |
| M4 | Schema validity of every record; unclassified inventory attributes (target 0) | validation report |
| M5 | Elapsed working time per procedure step | log below |
| M6 | Concepts that did not fit, with the reason | log below |

M5 is reported as context only: the implementation is AI-assisted, so time
does not measure the effort of an unassisted adapter author.

## Outcome categories (decided in advance)

- **Fits core** — valid records, no contract or shared-code change.
- **Fits with extensions** — valid records; some photonic concepts only in
  `extensions`; no contract change.
- **Requires contract change** — at least one change under R-1.
- **Does not fit** — no valid record without redesign.

## Threats

The same team designed the contract and performs the integration; the
integration is AI-assisted; one provider and one paradigm cannot establish
generality. These are reported with the result.

## Log

| Date (UTC) | Step | Note |
|---|---|---|
| 2026-11-19 | protocol | Written and committed before step 1. |
| 2026-11-19 | 1 probe | Token accepted on per-platform endpoints (`/api/platforms/<name>/`, Perceval 1.3.1); the listing endpoint `/api/platforms` answers 401 "Invalid token". Free plan: `sim:belenos`, `qpu:belenos`, `qpu:ascella` readable, `sim:altair` 403. `qpu:belenos` in `maintenance`. Evidence: `captures/quandela/platforms-2026-11-19.json`. |
| 2026-11-19 | 1 probe | Characterization (`perfs`: HOM 88.2 %, g2 1.3 %, per-mode transmission, per-detector dark counts, clock) has **no timestamp**. Specs expose detector type (`threshold`), mode/photon constraints, `pcvl_version`, `software_versions`, known mitigations. Results are Fock-state `samples` / `sample_count` / `probs`. |
| 2026-11-19 | 1 probe | Observation for step 2 (M6): the reduced `v0.1.0` contract has **no `extensions` member** (Listing 1 of the conceptual API has one); `Device` has `qubit_count` only; `measurement_counts` keys are unconstrained but described as bitstrings. Photonic structure (modes, photons, detector type) has no place in the frozen contract. |
| 2026-11-19 | 2 mapping | Mapping table committed before implementation: [quandela-mapping.md](quandela-mapping.md). Expected outcome: requires contract change (CC-1 `extensions`, CC-2 `results.outcome_basis`); inventory gaps reported (qubit count, IonQ-only probability applicability). |
| 2026-11-19 | R-1 CC-1 | Contract change: optional `extensions` member on `ProvenanceRecord`, keys `<paradigm>.<provider>`, object values. Forced by photonic structure (modes, photons, detector type, per-mode arrays, mitigations) having no core place; the conceptual API (Listing 1, P2) already had it. Files (M1): `openapi.json` (contract change), `models.py`, `adapter.py`, `service.py` (shared-code change needed to carry it, +6 LOC). Additive: all existing example records validate unchanged. Schema version left at `0.1.0-prototype` until the v0.2.0 release. |
