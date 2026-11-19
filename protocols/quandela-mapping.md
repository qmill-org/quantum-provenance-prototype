# Mapping table — Quandela Cloud → `v0.1.0` record (protocol step 2)

Prepared before any Quandela adapter code (see
[new-provider-quandela.md](new-provider-quandela.md)). Sources: the read-only
platform probe (`captures/quandela/platforms-2026-11-19.json`) and the
Quandela client (Perceval 1.3.1 `RPCHandler`, `RemoteJob`, `ExecutionStatus`).
**V** marks fields documented in the client but not yet seen in a real job
response; they are verified in step 4.

Fit categories: **core** (maps to an existing contract field with an
accurate meaning), **core — ambiguous** (schema-valid but the field's meaning
does not match), **extension** (needs the `extensions` member, absent from the
`v0.1.0` contract), **not representable**.

## 1. The 21 inventory attributes

| Inventory attribute | Quandela source | Record location | Evidence state | Fit |
|---|---|---|---|---|
| `job.status` | job status (`SUCCESS`, `ERROR`, `CANCELED`, …) **V** | `/job/status` | provider_supplied | core |
| `job.created_at` | `creation_datetime` (epoch seconds) **V** | `/job/created_at` | provider_supplied | core |
| `job.ended_at` | `start_time` + `duration` **V** | `/job/ended_at` | derived | core |
| `job.shots` | `max_shots` / `max_samples` job parameter **V** | `/job/shots` | provider_supplied if returned, else application_captured | core — ambiguous: photonic jobs bound *shots* (photon-detection events) and *samples* (post-selected outputs) separately |
| `device.identifier` | platform name (`qpu:belenos`, `sim:belenos`) | `/device/identifier` | provider_supplied | core |
| `device.type` | `type` (`qpu`, `simulator`) | `/device/type` | provider_supplied | core |
| `device.qubit_count` | none; capacity is `max_mode_count` 24, `max_photon_count` 12 | `/device/qubit_count` | — | **not representable** in core (inventory rule `all` makes it `unavailable`, which is misleading) → extension |
| `device.platform_provider` | Quandela Cloud | `/device/platform_provider` | provider_supplied | core |
| `device.hardware_provider` | Quandela | `/device/hardware_provider` | provider_supplied | core |
| `artifact.compiled` | not exposed by the platform API; compilation to the chip happens server-side **V** | `/artifacts[role=compiled]` | unavailable (not_exposed_by_provider) | core |
| `execution.queue_duration_ms` | `start_time − creation_datetime` **V** | `/execution/queue_duration_ms` | derived | core |
| `execution.run_duration_ms` | `duration` **V** | `/execution/run_duration_ms` | provider_supplied | core |
| `execution.total_duration_ms` | queue + run | `/execution/total_duration_ms` | derived | core |
| `characterization` | `perfs` (HOM, g2, transmission per mode, dark counts per detector, clock); **no timestamp** | `/characterization` (association `current_at_retrieval`, no `captured_at`) | provider_supplied | core for the scalar metrics; per-mode and per-detector arrays → extension |
| `results.measurement_counts` | `sample_count` results keyed by Fock state (`\|1,0,1,0>`) **V** | `/results/measurement_counts` | provider_supplied | **core — ambiguous**: keys are photon-number states, contract describes bitstrings |
| `results.measurement_probabilities` | `probs` results (simulator) **V** | `/results/measurement_probabilities` | provider_supplied | core — ambiguous (same); inventory marks it applicable to IonQ only, so a supplied value classifies `not_applicable` |
| `results.estimated_measurement_counts` | — | — | not_applicable | core (inventory rule is IonQ-only) |
| `compilation.compiler` | application side: Perceval (`pcvl_version`) builds the experiment; server-side compiler not exposed | `/compilation/compiler_name` | application_captured | core |
| `compilation.logical_to_physical_mapping` | input-state modes chosen by the application among `connected_input_modes` | `/compilation/logical_to_physical_mapping` | application_captured | core — ambiguous: mode mapping, not qubit mapping |
| `software.provider_client` | `perceval-quandela` version | `/software/provider_client` | application_captured | core |
| `software.framework_versions` | `pcvl_version`, `software_versions` (platform side) | `/software/framework_versions` | application_captured / provider_supplied | core |

## 2. Photonic concepts outside the inventory (rubric analogues)

| Rubric attribute | Quandela source | Fit |
|---|---|---|
| Q4 Program width (modes, input photons) | experiment input state, `max_mode_count`, `max_photon_count` | extension |
| QC3 Connectivity | `connected_input_modes`, universal interferometer | extension |
| QC5 Operation quality | `HOM (%)`, `g2 (%)`, `Transmittance (%)` | core (scalar characterization metrics) |
| QC5 per-mode transmission | `Transmission per mode` `t_in[]`, `t_out[]` | extension (arrays) |
| QC7 Read-out quality | `detector` = `threshold`; `Dark counts` per detector | detector type → extension; dark counts array → extension |
| QC6 Timing | `Clock (MHz)` | core (scalar metric) |
| E7 Error mitigation | `known_mitigations`, `default_mitigations` (PhotonRecycling, …) | extension (no mitigation field in contract) |
| S1 Backend software version | `software_versions`, `pcvl_version` of the platform | core (`/software`) |
| Result basis | Fock states vs bitstrings | needs an explicit field (see CC-2) |

## 3. Proposed contract changes (each made and logged separately under R-1)

| ID | Change | Why | Compatibility |
|---|---|---|---|
| CC-1 | Optional top-level `extensions` object; keys are namespaces `<paradigm>.<provider>` (e.g. `photonic.quandela`), values are objects. | Photonic structure (modes, photons, detector type, per-mode arrays, mitigations) has no core place; the conceptual API (paper Listing 1, P2) already specifies `extensions`, but the reduced contract omitted it. | Additive; existing records stay valid. |
| CC-2 | Optional `results.outcome_basis` enum: `bitstring`, `fock_state`, `site_occupation`, `other`. | The same `measurement_counts` field otherwise silently means different things; the schema already accepts Fock keys while describing bitstrings. | Additive; absent means `bitstring` for `v0.1.0` records. |

Not proposed: a core `device.capacity` field. Modes and photons go to
`extensions`; `device.qubit_count` is reported as a gap of the inventory,
which is not edited (R-2).

## 4. Expected outcome (stated before implementation)

**Requires contract change** (CC-1, CC-2), with most attributes fitting the
core. The 21-attribute inventory itself shows two generalization gaps
(`device.qubit_count` and the IonQ-only applicability rules for
probabilities), which are reported, not fixed.
