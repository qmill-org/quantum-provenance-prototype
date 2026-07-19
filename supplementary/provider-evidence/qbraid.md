# Evidence ledger — qBraid

**Classification:** cloud aggregator

**Evidence boundary:** This ledger covers publicly available qBraid
documentation, the open-source qBraid SDK source code, package documentation,
worked examples, and release notes. No claim of authenticated operational
verification is made; interface behavior is assessed through public artifacts
only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| qBraid documentation | Current public release | Official documentation | https://docs.qbraid.com/ | 2026-07-19 | Platform overview; supported providers and devices; job submission; result retrieval; access model |
| qBraid SDK documentation | Current public release | Official documentation | https://sdk.qbraid.com/ | 2026-07-19 | `QuantumJob` interface; `QuantumDevice` abstraction; result format; provider-agnostic job management |
| qBraid SDK (open source) | latest stable release | SDK source / package documentation | https://github.com/qBraid/qBraid | 2026-07-19 | `QuantumJob` class hierarchy; `GateModelJobResult` and related result types; `QuantumDevice` interface; provider adapter pattern |
| qbraid PyPI releases | latest stable | Package release page | https://pypi.org/project/qbraid/ | 2026-07-19 | Published release history and version constraints |
| qBraid API reference | Current public release | API reference | https://docs.qbraid.com/api-reference | 2026-07-19 | REST endpoint definitions for job submission, retrieval, and device listing; job status fields |

## Notes

- qBraid is a **cloud aggregator**: it provides access to hardware from
  multiple independent hardware providers through a common platform, account,
  and job-management interface. The qBraid SDK abstracts over provider
  differences through a provider-adapter architecture.
- The `QuantumJob` abstraction in the qBraid SDK provides uniform access to
  job status (`status()`), results (`result()`), and metadata across providers.
  The `GateModelJobResult` type normalizes gate-model results (measurement
  counts) into a common representation.
- Result payload normalization in qBraid SDK means that some provider-specific
  provenance fields (beyond measurement counts and standard job metadata) may
  not be surfaced through the provider-neutral interface; retrieving full
  provider-specific provenance may require accessing the raw result or using the
  provider's native SDK.
- qBraid also provides a hosted development environment (qBraid Lab) and
  additional services beyond job execution; these are not assessed here.
- The documented interface structure is established through the open-source
  qBraid SDK. Live field population for every provider target, device, or
  account configuration was not verified through authenticated access.
