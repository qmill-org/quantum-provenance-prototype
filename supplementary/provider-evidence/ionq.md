# Public evidence — IonQ

The IonQ fixtures reconstruct the shape of the IonQ jobs API, whose defining
characteristic is that results are returned as a **probability histogram** and
not as raw shot counts. All values in the fixtures are synthetic placeholders;
only the structure and field semantics are taken from the documentation below.

## Documentation sources (by name)

- **IonQ API documentation** — job submission and retrieval, including the
  normalized probability `histogram` keyed by integer state index, job status,
  and targets (e.g. `qpu.aria-1`, `simulator`).
  Root: https://docs.ionq.com/
- **IonQ provider integrations** (open source, e.g. `qiskit-ionq`) — job result
  handling that surfaces probabilities rather than counts.
  Root: https://github.com/Qiskit-Partners/qiskit-ionq

## What the fixture captures

- A completed job snapshot (status, timestamps, shots, target).
- A probability histogram (`result.raw_payload.histogram`).
- A compiled program passed through verbatim.
- A characterization/calibration document.

## What the fixture omits or synthesizes

- All account identifiers and API keys are placeholders (`FAKE-*`).
- Histogram and calibration values are representative, not measured.

## Why this provider matters for the model

IonQ returns probabilities, not counts. The unified model preserves this
faithfully: `measurement_probabilities` are recorded as `provider_supplied`, and
`estimated_measurement_counts` are recorded as `derived` (independent per-bucket
rounding of `probabilities x shots`). Raw `measurement_counts` are **never
fabricated**, because the provider does not supply them.
