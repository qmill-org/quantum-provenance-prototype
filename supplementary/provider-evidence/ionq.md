# Evidence ledger — IonQ

**Classification:** hardware-provider platform (trapped-ion)

**Evidence boundary:** This ledger covers publicly available IonQ API
documentation, maintained open-source SDK source code and package
documentation, worked examples, and release notes. No claim of authenticated
operational verification is made; interface behavior is assessed through public
artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| IonQ API documentation | v0.3 REST API | Official documentation | https://docs.ionq.com/ | 2026-07-19 | Job submission and retrieval; `histogram` probability result format; job status lifecycle; target specification (`qpu.aria-1`, `simulator`) |
| IonQ API reference (OpenAPI) | v0.3 | API reference / OpenAPI specification | https://docs.ionq.com/api-reference/ | 2026-07-19 | Request/response schemas; job fields (`id`, `status`, `target`, `shots`, `created_at`, `updated_at`); result histogram structure |
| qiskit-ionq (open source) | latest main branch | SDK source / package documentation | https://github.com/Qiskit-Partners/qiskit-ionq | 2026-07-19 | Probability-histogram result handling; IonQ job submission through Qiskit backend interface |
| qiskit-ionq PyPI releases | latest stable | Package release page | https://pypi.org/project/qiskit-ionq/ | 2026-07-19 | Published release history and version constraints |
| IonQ characterization / calibration documentation | Current public docs | Official documentation | https://docs.ionq.com/ | 2026-07-19 | Calibration data structure; native gate fidelities; qubit characterization fields |

## Notes

- The IonQ API returns results as a normalized probability **histogram** keyed
  by integer state index, not as raw shot counts. The unified model preserves
  this: `measurement_probabilities` are recorded as `provider_supplied`, and
  `estimated_measurement_counts` are recorded as `derived` (independent
  per-bucket rounding of `probabilities × shots`). Raw `measurement_counts` are
  never fabricated because the provider does not supply them.
- All account identifiers and API keys in the prototype fixtures are
  placeholders (`FAKE-*`).
- Histogram and calibration values in the fixtures are representative, not
  measured from a live backend.
- The documented interface structure is established; live field population
  (i.e. which exact calibration fields are populated for every account, target,
  or job type) was not verified through authenticated access.

## Legacy fixture evidence note

The prototype fixture (`tests/fixtures/ionq/`) reconstructs the IonQ jobs API
shape. Field paths and semantics are taken from the documentation sources
above; all values are synthetic placeholders. See also the original
fixture-focused evidence note, which this ledger supersedes.
