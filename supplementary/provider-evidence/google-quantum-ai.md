# Evidence ledger — Google Quantum AI

**Classification:** hardware-provider platform (superconducting)

**Evidence boundary:** This ledger covers publicly available Google Quantum AI
documentation, the open-source Cirq framework and cirq-google extension source
code, package documentation, worked examples, and release notes. No claim of
authenticated operational verification is made; interface behavior is assessed
through public artifacts only. Access to the Google Quantum Computing Service
(QCS) is by invitation; the service interface is assessed through the
open-source cirq-google library and its public documentation.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Google Quantum AI documentation | Public documentation reviewed 2026-07-19 | Official documentation | https://quantumai.google/ | 2026-07-19 | Platform overview; hardware systems (Sycamore); Cirq ecosystem |
| Cirq documentation | Cirq 1.7.0 documentation | Official documentation | https://quantumai.google/cirq | 2026-07-19 | Circuit model; result object (`cirq.Result`); measurement key structure; repetitions |
| Cirq GitHub repository (open source) | Cirq 1.7.0 | SDK source / package documentation | https://github.com/quantumlib/Cirq | 2026-07-19 | `cirq.Result` fields; `cirq.study.ResultTypes`; measurement data as NumPy arrays |
| cirq-google (open source) | Cirq 1.7.0 / Quantum Engine API client surface | SDK source / package documentation | https://github.com/quantumlib/Cirq/tree/main/cirq-google | 2026-07-19 | `Engine` and `EngineJob` interfaces; `QuantumExecutable` submission; calibration data structures; processor/device specification |
| cirq-google PyPI releases | cirq-google package at Cirq 1.7.0 cutoff | Package release page | https://pypi.org/project/cirq-google/ | 2026-07-19 | Published release history and version constraints |
| Cirq release notes | Cirq 1.7.0 release notes | Release notes | https://github.com/quantumlib/Cirq/releases | 2026-07-19 | Version-specific interface changes |

## Notes

- Google Quantum Computing Service (QCS) access is by invitation only.
  The programmatic interface is assessed through the public `cirq-google`
  open-source library, which defines the `Engine`, `EngineJob`, and
  `EngineProcessor` interfaces.
- `cirq.Result` documents measurement outcomes as a dictionary of measurement
  keys to NumPy integer arrays (shape: `repetitions × qubits`). This differs
  from both count-histogram (IBM, Braket) and probability-histogram (IonQ)
  interfaces; the unified model records raw measurement arrays as
  `provider_supplied` where applicable.
- Device calibration data is accessible through `EngineProcessor` calibration
  methods in cirq-google; the exact fields (Pauli error rates, T1, readout
  fidelities) are documented in the calibration result type.
- Google Quantum AI is not among the three providers with prototype fixtures in
  this repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the open-source
  cirq-google library. Live field population for every processor, account, or
  job configuration was not verified through authenticated access.
