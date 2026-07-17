# Public evidence — Amazon Braket

The Braket fixtures reconstruct the shape of two public Braket APIs. All values
in the fixtures are synthetic placeholders; only the structure and field
semantics are taken from the documentation below.

## Documentation sources (by name)

- **Amazon Braket Developer Guide** — task lifecycle, task result format
  (`measurementCounts`), and device ARNs.
  Root: https://docs.aws.amazon.com/braket/
- **Amazon Braket API Reference** — `GetQuantumTask` (status, `createdAt`,
  `endedAt`, `shots`, `deviceArn`) and `GetDevice` (device type, status,
  provider properties, calibration).
  Root: https://docs.aws.amazon.com/braket/latest/APIReference/
- **amazon-braket-sdk-python** (open source) — result object schema and the
  `measurement_counts` accessor used to reconstruct the fixture.
  Root: https://github.com/amazon-braket/amazon-braket-sdk-python

## What the fixture captures

- A completed task snapshot (status, timestamps, shots, device ARN).
- A measurement-count histogram (`result.measurement_counts`).
- A native compiled program passed through verbatim.
- A device document (type, status, provider properties, calibration).

## What the fixture omits or synthesizes

- All account identifiers, ARNs, and credentials are placeholders (`FAKE-*`).
- Calibration values are representative, not measured from a real device.
- The hardware provider is inferred from the (synthetic) device ARN, mirroring
  how Braket brokers multiple hardware providers.
