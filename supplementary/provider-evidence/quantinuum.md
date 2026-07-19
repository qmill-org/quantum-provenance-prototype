# Evidence ledger — Quantinuum

**Classification:** hardware-provider platform (trapped-ion)

**Evidence boundary:** This ledger covers publicly available Quantinuum
documentation, Nexus API materials, maintained SDK source code and package
documentation, worked examples, and release notes. No claim of authenticated
operational verification is made; interface behavior is assessed through public
artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Quantinuum documentation portal | Public documentation reviewed 2026-07-19 | Official documentation | https://docs.quantinuum.com/ | 2026-07-19 | Platform overview; H-Series trapped-ion systems; access model; Nexus platform context |
| Quantinuum Nexus API documentation | Nexus HTTP API / OpenAPI | Official documentation | https://docs.quantinuum.com/nexus/ | 2026-07-19 | Current remote job-management interface; endpoint and payload structure for execution and retrieval |
| qnexus (open source) | `qnexus` 0.46.0 | SDK source / package documentation | https://github.com/CQCL/qnexus | 2026-07-19 | Current Python client for Nexus API; job submission, status polling, and result retrieval surfaces |
| qnexus PyPI releases | `qnexus` 0.46.0 | Package release page | https://pypi.org/project/qnexus/ | 2026-07-19 | Published release history and version constraints |
| pytket (open source) | Supplementary compilation/result-model evidence reviewed 2026-07-19 | SDK source / package documentation | https://github.com/CQCL/pytket | 2026-07-19 | Circuit and result object semantics used in the broader Quantinuum software stack |
| pytket-quantinuum (open source) | Supplementary legacy integration evidence reviewed 2026-07-19 | SDK source / package documentation | https://github.com/CQCL/pytket-quantinuum | 2026-07-19 | Historical backend adapter references retained as supplementary evidence only |

## Notes

- Quantinuum (formerly Cambridge Quantum and Honeywell Quantum Solutions)
  provides H-Series trapped-ion systems. For the paper assessment, the current
  remote-access interface is the Nexus HTTP API/OpenAPI plus the `qnexus`
  client at version 0.46.0.
- `pytket` result semantics (shot tables, count dictionaries, and state
  dictionaries) are retained as supplementary evidence for result-shape
  interpretation, but are not treated here as the current remote access API.
- Quantinuum H-Series systems expose calibration and device-performance
  information through documented interfaces; evidence here remains limited to
  public documentation and SDK artifacts.
- Quantinuum is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the Nexus API
  documentation and maintained SDK/package sources listed above. Live field
  population for every system generation, account type, or job configuration
  was not verified through authenticated access.
