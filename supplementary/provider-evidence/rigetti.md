# Evidence ledger — Rigetti Computing

**Classification:** hardware-provider platform (superconducting)

**Evidence boundary:** This ledger covers publicly available Rigetti
documentation, the Quantum Cloud Services (QCS) API reference, maintained
open-source PyQuil SDK source code, package documentation, worked examples,
and release notes. No claim of authenticated operational verification is made;
interface behavior is assessed through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Rigetti QCS documentation | Current public release | Official documentation | https://docs.rigetti.com/qcs/ | 2026-07-19 | Platform overview; QPU and QVM targets; job execution lifecycle; reservation model; result format |
| Rigetti QCS API reference | Current public release | API reference / OpenAPI specification | https://docs.api.qcs.rigetti.com/ | 2026-07-19 | REST endpoint definitions; `QuantumProcessor` fields; `ExecutionResult` fields; `ReadoutValues` structure (register name → per-shot integer array); job status |
| PyQuil documentation | Current public release | Official documentation | https://pyquil-docs.rigetti.com/ | 2026-07-19 | Quil circuit language; `QPUExecutor` usage; result `ReadoutData` format; compiler integration |
| PyQuil (open source) | latest stable release | SDK source / package documentation | https://github.com/rigetti/pyquil | 2026-07-19 | `QuantumComputer` interface; `Program` execution; `QAMExecutionResult` and `ReadoutData` objects; register-keyed measurement results |
| pyquil PyPI releases | latest stable | Package release page | https://pypi.org/project/pyquil/ | 2026-07-19 | Published release history and version constraints |
| qcs-sdk-python (open source) | latest stable release | SDK source / package documentation | https://github.com/rigetti/qcs-sdk-python | 2026-07-19 | Lower-level QCS API client; quilc compilation; `ExecutionResult` deserialization |

## Notes

- Rigetti's QCS API is publicly documented with an OpenAPI specification,
  making it one of the better-documented REST interfaces among the analyzed
  hardware providers. The `docs.api.qcs.rigetti.com` reference provides stable
  endpoint and schema documentation.
- Measurement results are returned as register-keyed arrays: each named
  `MEASURE` target in the Quil program corresponds to a register name, and the
  result contains a per-shot array of integer values for that register.
  This differs from both bitstring-histogram (IBM/Braket) and probability-
  histogram (IonQ) interfaces.
- QPU characterization data (qubit T1/T2, gate fidelities, readout fidelities)
  is accessible through the `GetQuantumProcessor` API endpoint; calibration
  data freshness is documented in terms of calibration job timestamps.
- The QCS API supports both direct QPU execution and Quantum Virtual Machine
  (QVM) simulation; provenance fields specific to QPU execution (e.g.
  calibration, hardware topology) are not applicable to QVM runs.
- Rigetti is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the public QCS API
  reference and open-source PyQuil SDK. Live field population for every QPU
  generation, compiler configuration, or account type was not verified through
  authenticated access.
