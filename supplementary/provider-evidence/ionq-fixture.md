# Public evidence — IonQ fixture companion note

The IonQ fixture reconstructs the public IonQ jobs API shape for the prototype
evaluation boundary. All values are synthetic placeholders; only structure and
field semantics are reconstructed from public documentation and open-source SDK
evidence.

## Fixture boundary and key semantics

- **Synthetic fixture boundary:** the fixture is hand-authored and sanitized;
  no authenticated operational verification or live account captures are
  claimed.
- **Probability histogram, not observed counts:** IonQ results are represented
  as a normalized histogram (`result.raw_payload.histogram`) keyed by integer
  state index.
- **Completed-job coverage:** fixture fields cover completed-job status,
  timestamps, shot count, and target identifiers.
- **Compiled-program coverage:** the fixture carries a compiled/native program
  payload that is passed through as provider evidence.
- **Characterization coverage:** the fixture includes a provider-linked
  characterization/calibration document.
- **Derived estimated counts:** `estimated_measurement_counts` are derived from
  `histogram × shots` with per-bucket rounding; they are explicitly derived and
  are not provider-supplied observed counts.

## Relationship to the full IonQ ledger

For full comparative evidence-table coverage in the 15-platform analysis, see
[`ionq.md`](ionq.md). This companion note exists to preserve fixture-specific
mapping context alongside the corresponding Braket and IBM fixture notes.
