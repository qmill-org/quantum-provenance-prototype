# Platform-specific findings (detailed supplementary profile)

This detailed profile is the evidence-safe counterpart to the paper's condensed
platform-specific findings. It preserves only claims grounded in the repository
sources: provider evidence ledgers, fixture companion notes, provider-profile
JSON files, and repository documentation.

## Evidence boundary

All sections below use the same boundary: public documentation, public schemas,
maintained SDK source/models, package documentation, worked examples, and
release notes. No section claims authenticated operational verification.

## Hardware-provider platforms (12)

### AQT (Alpine Quantum Technologies)

- **Assessed interfaces/versions:** Qiskit AQT Provider 1.15.0; AQT Public API
  1.1.1; OpenAPI 3.1.
- **Detailed findings:** Public evidence supports a trapped-ion, shot-sample
  oriented interface through the Qiskit provider ecosystem. Result structure is
  documented as per-shot measurement samples rather than probability histograms.
- **Assessment summary:** Interface structure is documented and version-pinned
  for comparative analysis; no authenticated runtime behavior is claimed.
- **Comparative evidence ledger:** [AQT](../provider-evidence/aqt.md)

### D-Wave

- **Assessed interfaces/versions:** Ocean SDK 9.3.0; SAPI `/sapi/v2`; version-3
  solver representations.
- **Detailed findings:** Evidence reflects annealing and hybrid workflows via
  Ocean toolchains and SAPI responses (`SampleSet`, timing metadata, solver
  descriptors). This differs semantically from gate-model count/probability
  outputs.
- **Assessment summary:** Comparative position is supported for annealing-style
  payloads and metadata surfaces under the assessed Ocean/SAPI versions.
- **Comparative evidence ledger:** [D-Wave](../provider-evidence/d-wave.md)

### Google Quantum AI

- **Assessed interfaces/versions:** Cirq 1.7.0; Quantum Engine API.
- **Detailed findings:** Public materials support Cirq result and measurement-key
  structures, plus Engine submission/retrieval abstractions and processor
  metadata surfaces.
- **Assessment summary:** Assessed interfaces establish public structural
  comparability without asserting authenticated execution behavior.
- **Comparative evidence ledger:** [Google Quantum AI](../provider-evidence/google-quantum-ai.md)

### IBM Quantum

- **Assessed interfaces/versions:** Qiskit SDK 2.5.0; Qiskit IBM Runtime 0.47.0;
  Qiskit Runtime REST API 2026-04-15.
- **Detailed findings:** Evidence and fixture-oriented material align on runtime
  job lifecycle fields, count-based primitive results, transpiled/ISA program
  handling, and backend-property characterization snapshots.
- **Assessment summary:** Version-pinned interfaces support direct-provider
  comparative claims and fixture-compatibility interpretation.
- **Comparative evidence ledger:** [IBM Quantum](../provider-evidence/ibm-quantum.md)

### IonQ

- **Assessed interfaces/versions:** Qiskit IonQ Provider 1.1.1; IonQ Quantum
  Cloud API v0.4.
- **Detailed findings:** IonQ surfaces normalized probability histograms keyed by
  integer state index; derived estimated counts remain application-derived.
  Fixture companion material confirms this distinction and the characterization
  boundary used in the prototype narrative.
- **Assessment summary:** Evidence supports probability-first semantics and
  explicit derived-field treatment in cross-platform comparisons.
- **Comparative evidence ledger:** [IonQ](../provider-evidence/ionq.md)

### IQM

- **Assessed interfaces/versions:** IQM Client 34.0.4.
- **Detailed findings:** Public evidence supports REST-oriented submission and
  retrieval models with IQM circuit/result structures; supplementary
  qiskit-on-iqm sources are treated as integration context rather than the
  primary assessed interface.
- **Assessment summary:** Assessed client/API materials are sufficient for
  comparative interface-structure claims at the July 2026 cutoff.
- **Comparative evidence ledger:** [IQM](../provider-evidence/iqm.md)

### Pasqal

- **Assessed interfaces/versions:** Pulser 1.8.0; `pasqal-cloud` 0.23.0; Pasqal
  Cloud OpenAPI 3.0.2.
- **Detailed findings:** Public sources support neutral-atom pulse-sequence
  modeling (`Pulser`) with cloud job orchestration via `pasqal-cloud` and
  corresponding API-schema context.
- **Assessment summary:** Comparative claims for Pasqal are grounded in
  version-pinned pulse-level and cloud-interface evidence.
- **Comparative evidence ledger:** [Pasqal](../provider-evidence/pasqal.md)

### Quandela

- **Assessed interfaces/versions:** Perceval documentation 1.2; source release
  1.2.4; PyPI package at cutoff 1.2.3.
- **Detailed findings:** Public evidence supports photonic circuit abstractions,
  boson-sampling-style output distributions, and cloud-managed execution
  semantics through the Perceval ecosystem.
- **Assessment summary:** Versioned documentation/source/package evidence is
  preserved distinctly for this photonic interface family.
- **Comparative evidence ledger:** [Quandela](../provider-evidence/quandela.md)

### Quantinuum

- **Assessed interfaces/versions:** `qnexus` 0.46.0; Nexus HTTP API/OpenAPI.
- **Detailed findings:** The assessed current remote-access interface is Nexus
  API plus `qnexus`. `pytket` and `pytket-quantinuum` are retained as
  supplementary historical/result-model context only, not as the current primary
  remote API for paper claims.
- **Assessment summary:** Ledger alignment now follows the paper's assessed
  interface focus and avoids substituting retired legacy API framing.
- **Comparative evidence ledger:** [Quantinuum](../provider-evidence/quantinuum.md)

### QuEra through Amazon Braket

- **Assessed interfaces/versions:** Amazon Braket SDK 1.123.0; authenticated
  Braket API; AHS schema.
- **Detailed findings:** Evidence captures QuEra access through Braket surfaces,
  including AHS task/result schema context and brokered device identity
  semantics.
- **Assessment summary:** Comparative treatment remains explicitly brokered
  (aggregator-mediated), not direct standalone QuEra cloud API verification.
- **Comparative evidence ledger:** [QuEra](../provider-evidence/quera.md)

### Rigetti

- **Assessed interfaces/versions:** pyQuil 4.17.0; QCS SDK; `quilc`; HTTP
  OpenAPI and gRPC services.
- **Detailed findings:** Public materials support Quil/pyQuil execution and
  register-keyed readout structures, with QCS service surfaces documented via
  HTTP API and gRPC-oriented SDK materials.
- **Assessment summary:** Versioned pyQuil evidence plus QCS interface artifacts
  support comparative claims for direct-provider gate-model workflows.
- **Comparative evidence ledger:** [Rigetti](../provider-evidence/rigetti.md)

### VTT QX

- **Assessed interfaces/versions:** Q50 support window at cutoff: IQM Client
  34–35 and IQM Pulla 13–14.
- **Detailed findings:** Public VTT service descriptions plus IQM interface
  materials establish supported access and result-structure context for the
  VTT/IQM stack at the evaluation cutoff.
- **Assessment summary:** Comparative treatment is bounded to documented support
  windows and public interface artifacts.
- **Comparative evidence ledger:** [VTT QX](../provider-evidence/vtt-qx.md)

## Cloud aggregators (3)

### Amazon Braket

- **Assessed interfaces/versions:** Amazon Braket SDK 1.123.0; Braket service
  API.
- **Detailed findings:** Public evidence supports common task/device APIs that
  broker multiple hardware providers; fixture-oriented Braket context in this
  repository remains synthetic and structurally reconstructed.
- **Assessment summary:** Aggregator-level comparability is grounded in unified
  API semantics and explicit provider-brokering behavior.
- **Comparative evidence ledger:** [Amazon Braket](../provider-evidence/amazon-braket.md)

### Microsoft Azure Quantum

- **Assessed interfaces/versions:** QDK 1.30.0; Azure Quantum Python SDK 3.10.0;
  data-plane REST API `2026-01-15-preview`.
- **Detailed findings:** Public sources establish aggregator workflows over
  workspace/job abstractions with provider-mediated outputs and target metadata.
- **Assessment summary:** Version-pinned SDK/REST evidence supports cloud
  aggregator comparison without authenticated tenant-level verification.
- **Comparative evidence ledger:** [Azure Quantum](../provider-evidence/azure-quantum.md)

### qBraid

- **Assessed interfaces/versions:** qBraid SDK 0.12.2; Quantum Runtime API.
- **Detailed findings:** Evidence supports provider-agnostic job/device
  abstractions and runtime API surfaces for submission, retrieval, and status.
- **Assessment summary:** Public SDK/API artifacts are sufficient for
  comparative aggregator interpretation at cutoff.
- **Comparative evidence ledger:** [qBraid](../provider-evidence/qbraid.md)

## Cross-platform interpretation

- The assessed set remains **15 platforms total**: 12 hardware-provider
  platforms plus 3 cloud aggregators.
- Result semantics are intentionally not homogenized in source evidence:
  histogram/probability-first, count-first, shot-table, annealing sample-set,
  and analog/photonic forms are all preserved before unified-model mapping.
- Aggregator evidence (Braket, Azure Quantum, qBraid) is interpreted as
  broker-interface evidence and kept distinct from direct-provider API evidence.
- Fixture-specific mapping material remains limited to the prototype-supported
  providers (Braket, IBM, IonQ) and does not expand authenticated claims.

## Excluded/retired note

- **Xanadu Cloud** is excluded from the active 15-platform comparative set in
  this branch state because it is treated as retired/not in active scope at the
  paper cutoff. The exclusion note is preserved to avoid backfilling claims with
  non-current interfaces.
