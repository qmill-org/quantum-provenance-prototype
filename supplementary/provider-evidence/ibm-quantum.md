# Evidence ledger — IBM Quantum

**Classification:** hardware-provider platform (superconducting)

**Evidence boundary:** This ledger covers publicly available IBM Quantum
documentation, maintained open-source Qiskit IBM Runtime SDK source code and
package documentation, worked examples, and release notes. No claim of
authenticated operational verification is made; interface behavior is assessed
through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| IBM Quantum documentation | Public documentation reviewed 2026-07-19 | Official documentation | https://docs.quantum.ibm.com/ | 2026-07-19 | Job lifecycle; primitive results; backend properties; calibration snapshot format |
| qiskit-ibm-runtime (open source) | Qiskit IBM Runtime 0.47.0 | SDK source / package documentation | https://github.com/Qiskit/qiskit-ibm-runtime | 2026-07-19 | `RuntimeJob` status and timestamp fields; primitive result data (bitstring counts); `backend.properties()` calibration structure; job metadata |
| qiskit-ibm-runtime PyPI releases | Qiskit IBM Runtime 0.47.0 | Package release page | https://pypi.org/project/qiskit-ibm-runtime/ | 2026-07-19 | Published release history and version constraints |
| IBM Quantum API reference | Qiskit Runtime REST API 2026-04-15 | API reference | https://docs.quantum.ibm.com/api/qiskit-ibm-runtime | 2026-07-19 | `RuntimeJob` class interface; job status enum (`DONE`, `RUNNING`, `ERROR`, `CANCELLED`); backend properties API |
| Qiskit documentation | Qiskit SDK 2.5.0 documentation | Official documentation | https://docs.quantum.ibm.com/api/qiskit | 2026-07-19 | Circuit representation; transpilation; ISA circuit concepts |

## Notes

- IBM Quantum provenance is fragmented across multiple resources: job metadata
  (job ID, status, timestamps, backend name) comes from the `RuntimeJob`
  object; measurement results (bitstring counts) come from the primitive result;
  device characterization comes from the separate `backend.properties()`
  calibration snapshot; and compilation artifacts come from the ISA/transpiled
  circuit.
- Characterization is recorded as `provider_supplied` with a
  **nearest-available** association: the backend-properties snapshot is not
  necessarily in force at execution time, and the temporal delta between
  calibration capture and job execution is reported explicitly.
- All account identifiers and access tokens in the prototype fixtures are
  placeholders (`FAKE-*`).
- Calibration values in the fixtures are representative, not measured from a
  real backend.
- The documented interface structure (field names, job/result/backend model) is
  established through the open-source SDK. Live field population for every
  account tier, backend, or region was not verified through authenticated access.

## Fixture companion note

The prototype fixture (`tests/fixtures/ibm/`) reconstructs the Qiskit Runtime
job/result and backend-properties API shape. See also the fixture-specific
companion note ([`ibm.md`](ibm.md)), which preserves the direct fixture mapping
detail for the three-provider prototype implementation.
