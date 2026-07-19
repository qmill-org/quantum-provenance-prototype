# Evidence ledger — Amazon Braket

**Classification:** cloud aggregator

**Evidence boundary:** This ledger covers publicly available Amazon Braket
developer and API documentation, maintained open-source SDK source code and
package documentation, worked examples, and release notes. No claim of
authenticated operational verification is made; interface behavior is assessed
through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Amazon Braket Developer Guide | No exact assessed version established in paper/profile (public release reviewed 2026-07-19) | Official documentation | https://docs.aws.amazon.com/braket/latest/developerguide/ | 2026-07-19 | Task lifecycle; task result format (`measurementCounts`); device ARN conventions; supported hardware providers |
| Amazon Braket API Reference | No exact assessed version established in paper/profile (public release reviewed 2026-07-19) | API reference | https://docs.aws.amazon.com/braket/latest/APIReference/ | 2026-07-19 | `GetQuantumTask` fields (`status`, `createdAt`, `endedAt`, `shots`, `deviceArn`); `GetDevice` fields (device type, status, provider properties, calibration) |
| amazon-braket-sdk-python (open source) | No exact assessed version established in paper/profile (latest stable release reviewed 2026-07-19) | SDK source / package documentation | https://github.com/amazon-braket/amazon-braket-sdk-python | 2026-07-19 | Result object schema; `measurement_counts` accessor; task result parsing; device properties models |
| amazon-braket-sdk-python PyPI releases | No exact assessed version established in paper/profile (latest stable release reviewed 2026-07-19) | Package release page | https://pypi.org/project/amazon-braket-sdk/ | 2026-07-19 | Published release history and version constraints |
| Amazon Braket pricing and device list | No exact assessed version established in paper/profile (public page reviewed 2026-07-19) | Official documentation | https://aws.amazon.com/braket/pricing/ | 2026-07-19 | Supported hardware providers brokered through aggregator interface |

## Notes

- Amazon Braket is a **cloud aggregator**: it brokers hardware from multiple
  independent hardware providers (including IonQ, IQM, QuEra, Rigetti, and
  others) through a common account, job-management interface, and execution API.
  The hardware provider is inferred from the device ARN structure.
- The prototype fixture reconstructs the shape of the `GetQuantumTask` and
  `GetDevice` (calibration) APIs. Field paths and semantics are taken from the
  documentation sources above; all values are synthetic placeholders (`FAKE-*`
  markers and example ARNs).
- Calibration values in the fixtures are representative, not measured from a
  real device.
- The documented interface structure (field names, nesting, data types) is
  established through the open-source SDK and API reference. Live field
  population (e.g. which calibration fields are present for every hardware
  provider, region, or device type) was not verified through authenticated
  access.
- The Braket--IonQ case and the direct IBM Quantum case form the principal
  aggregator-versus-direct-provider comparison in the prototype evaluation.

## Legacy fixture evidence note

The prototype fixture (`tests/fixtures/braket/`) reconstructs the Amazon Braket
task and device API shape. See also the fixture-specific companion note
([`braket.md`](braket.md)), which preserves the direct fixture mapping detail
for the three-provider prototype implementation.
