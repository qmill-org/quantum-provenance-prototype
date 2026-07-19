# Evidence ledger — AQT (Alpine Quantum Technologies)

**Classification:** hardware-provider platform (trapped-ion)

**Evidence boundary:** This ledger covers publicly available AQT API and portal
documentation, maintained open-source Qiskit AQT provider SDK source code and
package documentation, worked examples, and release notes. No claim of
authenticated operational verification is made; interface behavior is assessed
through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| AQT website and system overview | AQT Public API 1.1.1 (OpenAPI 3.1); public documentation reviewed 2026-07-19 | Official documentation | https://www.aqt.eu/ | 2026-07-19 | Platform overview; available trapped-ion systems; access model (cloud portal) |
| qiskit-aqt-provider (open source) | Qiskit AQT Provider 1.15.0 | SDK source / package documentation | https://github.com/qiskit-community/qiskit-aqt-provider | 2026-07-19 | Job submission and retrieval interface; result structure (measurement samples as bitstring list); job status fields; resource/target specification |
| qiskit-aqt-provider PyPI releases | Qiskit AQT Provider 1.15.0 | Package release page | https://pypi.org/project/qiskit-aqt-provider/ | 2026-07-19 | Published release history and version constraints |
| qiskit-aqt-provider documentation | Qiskit AQT Provider 1.15.0 documentation | Package documentation | https://qiskit-community.github.io/qiskit-aqt-provider/ | 2026-07-19 | API usage examples; supported gate set; result format documentation |

## Notes

- AQT provides access to trapped-ion quantum hardware through a cloud portal
  and a Qiskit-compatible provider. The `qiskit-aqt-provider` open-source
  package is the primary documented programmatic interface.
- Result samples are documented as a list of per-shot measurement bitstrings
  (not a histogram), which differs from IonQ's probability-histogram interface.
- A precise stable versioned documentation URL for the AQT API specification
  could not be independently verified beyond the open-source SDK and the
  official website. The SDK source code and package documentation are the
  principal evidence sources.
- All account tokens and workspace identifiers in any prototype fixtures would
  be placeholders; AQT is not among the three providers with prototype fixtures.
- The documented interface structure is established through the open-source SDK.
  Live field population for every account type, system, or job configuration
  was not verified through authenticated access.
