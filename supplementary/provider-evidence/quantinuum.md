# Evidence ledger — Quantinuum

**Classification:** hardware-provider platform (trapped-ion)

**Evidence boundary:** This ledger covers publicly available Quantinuum
documentation, maintained open-source pytket and pytket-quantinuum SDK source
code, package documentation, worked examples, and release notes. No claim of
authenticated operational verification is made; interface behavior is assessed
through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Quantinuum documentation portal | Current public release | Official documentation | https://docs.quantinuum.com/ | 2026-07-19 | Platform overview; H-Series trapped-ion systems; job submission; result format; access model |
| pytket documentation | Current public release | Official documentation | https://tket.quantinuum.com/api-docs/ | 2026-07-19 | Circuit model; `BackendResult` fields (shot table, state dict); compilation pipeline |
| pytket (open source) | latest stable release | SDK source / package documentation | https://github.com/CQCL/pytket | 2026-07-19 | `BackendResult` object; measurement outcome representations (shot table, counts dict, state vector, unitary) |
| pytket PyPI releases | latest stable | Package release page | https://pypi.org/project/pytket/ | 2026-07-19 | Published release history and version constraints |
| pytket-quantinuum (open source) | latest stable release | SDK source / package documentation | https://github.com/CQCL/pytket-quantinuum | 2026-07-19 | Quantinuum backend adapter; job submission to Quantinuum H-Series; result retrieval; device properties; status fields |
| pytket-quantinuum PyPI releases | latest stable | Package release page | https://pypi.org/project/pytket-quantinuum/ | 2026-07-19 | Published release history and version constraints |

## Notes

- Quantinuum (formerly Cambridge Quantum and Honeywell Quantum Solutions) provides
  H-Series trapped-ion systems. The `pytket-quantinuum` open-source backend
  adapter is the primary documented programmatic interface for result retrieval.
- `pytket`'s `BackendResult` supports multiple result representations:
  shot tables (per-shot bitstring lists), count dictionaries, and state
  dictionaries. The exact representation returned depends on the backend and
  configuration; shot tables and counts are the primary documented forms for
  H-Series QPU jobs.
- Quantinuum H-Series systems expose per-qubit and per-gate error rates and
  characterization data; these are accessible through the backend properties
  interface in `pytket-quantinuum`. A precise stable URL for the Quantinuum
  calibration API specification could not be independently verified beyond the
  open-source adapter.
- Quantinuum is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the open-source
  pytket and pytket-quantinuum packages. Live field population for every system
  generation, account type, or job configuration was not verified through
  authenticated access.
