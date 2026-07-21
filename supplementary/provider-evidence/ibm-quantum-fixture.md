# Public evidence — IBM Quantum

The IBM fixtures reconstruct the shape of the Qiskit Runtime job/result and
backend-properties APIs. All values in the fixtures are synthetic placeholders;
only the structure and field semantics are taken from the documentation below.

## Documentation sources (by name)

- **IBM Quantum documentation** — job lifecycle, primitive results, and backend
  properties/calibration.
  Root: https://docs.quantum.ibm.com/
- **qiskit-ibm-runtime** (open source) — `RuntimeJob` status/timestamps and the
  primitive result data (bitstring counts), plus `backend.properties()` used to
  reconstruct the calibration snapshot.
  Root: https://github.com/Qiskit/qiskit-ibm-runtime

## What the fixture captures

- A completed (`DONE`) job snapshot (status, timestamps, shots, backend name).
- Bitstring measurement counts (`result.measurement_counts`).
- An ISA/transpiled circuit used for execution.
- A backend-properties snapshot (qubit and gate calibration).

## What the fixture omits or synthesizes

- All account identifiers and access tokens are placeholders (`FAKE-*`).
- Calibration values are representative, not measured from a real backend.
- Characterization is recorded as `provider_supplied` with a **nearest-available**
  association: the reported temporal delta reflects that the calibration snapshot
  was not necessarily in force at execution time.
