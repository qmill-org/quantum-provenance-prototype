# Evidence ledger — Pasqal

**Classification:** hardware-provider platform (neutral-atom)

**Evidence boundary:** This ledger covers publicly available Pasqal
documentation, maintained open-source Pulser framework and pasqal-cloud SDK
source code, package documentation, worked examples, and release notes. No
claim of authenticated operational verification is made; interface behavior is
assessed through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Pasqal documentation | Current public release | Official documentation | https://docs.pasqal.com/ | 2026-07-19 | Platform overview; neutral-atom hardware (Fresnel, EMU); access model; job submission workflow |
| Pulser documentation | Current public release | Official documentation | https://pulser.readthedocs.io/ | 2026-07-19 | Pulse-sequence circuit model; register (atom layout); sequence serialization; result format |
| Pulser (open source) | latest stable release | SDK source / package documentation | https://github.com/pasqal-io/Pulser | 2026-07-19 | `Sequence` and `Register` objects; pulse-level circuit representation; device specification; result structure |
| Pulser PyPI releases | latest stable | Package release page | https://pypi.org/project/pulser/ | 2026-07-19 | Published release history and version constraints |
| pasqal-cloud (open source) | latest stable release | SDK source / package documentation | https://github.com/pasqal-io/pasqal-cloud | 2026-07-19 | Cloud job submission; `Batch` and `Job` objects; job status fields; result retrieval |
| pasqal-cloud PyPI releases | latest stable | Package release page | https://pypi.org/project/pasqal-cloud/ | 2026-07-19 | Published release history and version constraints |

## Notes

- Pasqal provides neutral-atom hardware where circuits are expressed as
  pulse sequences applied to configurable atom registers, rather than as
  sequences of standard gates. The `Pulser` framework is the primary
  circuit-description and submission tool.
- Result semantics differ from gate-based platforms: outcomes are counts of
  atom states (ground or excited) per shot across the register, rather than
  bitstring measurement counts. The unified model must accommodate this
  technology-specific result structure.
- The `pasqal-cloud` SDK documents job fields including job ID, status,
  timestamps, and result payload. A precise stable version of the cloud API
  OpenAPI specification could not be independently verified beyond the
  open-source client; the SDK source is the primary evidence for response
  field structure.
- Pasqal systems are also accessible through certain aggregator platforms
  (e.g. Amazon Braket); those access paths are covered under the respective
  aggregator ledgers.
- Pasqal is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the open-source
  Pulser and pasqal-cloud packages. Live field population for every device,
  region, or account type was not verified through authenticated access.
