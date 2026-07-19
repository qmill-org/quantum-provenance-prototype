# Evidence ledger — QuEra Computing

**Classification:** hardware-provider platform (neutral-atom)

**Evidence boundary:** This ledger covers publicly available QuEra
documentation, the open-source Bloqade neutral-atom programming framework
source code, package documentation, worked examples, release notes, and Amazon
Braket integration documentation for Aquila access. No claim of authenticated
operational verification is made; interface behavior is assessed through public
artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| QuEra documentation | Public documentation reviewed 2026-07-19 | Official documentation | https://docs.quera.com/ | 2026-07-19 | Platform overview; Aquila neutral-atom system; analog Hamiltonian simulation model; access model |
| Bloqade documentation | Supplementary documentation reviewed 2026-07-19 | Official documentation | https://queracomputing.github.io/bloqade-python/ | 2026-07-19 | Analog Hamiltonian simulation interface; register specification; drive and waveform construction; result format |
| bloqade-python (open source) | Supplementary source reviewed 2026-07-19 | SDK source / package documentation | https://github.com/QuEraComputing/bloqade-python | 2026-07-19 | `AtomArrangement`; pulse/waveform objects; `ShotResult` and `Report` result types; Braket backend integration |
| bloqade PyPI releases | Supplementary package releases reviewed 2026-07-19 | Package release page | https://pypi.org/project/bloqade/ | 2026-07-19 | Published release history and version constraints |
| Amazon Braket — Aquila device documentation | Amazon Braket SDK 1.123.0 + authenticated Braket API (AHS schema) | Official documentation | https://docs.aws.amazon.com/braket/latest/developerguide/braket-devices.html | 2026-07-19 | Aquila device ARN; task result format when accessed via Braket; `AHSQuantumTaskResult` structure |

## Notes

- QuEra's Aquila system is an analog Hamiltonian simulator, not a gate-based
  quantum computer. The computational model (driven evolution of atom registers
  under a specified Hamiltonian) differs fundamentally from both gate-based and
  quantum-annealing platforms. Provenance attributes such as gate fidelities
  and circuit depth are not applicable.
- Aquila is accessible through Amazon Braket (as the primary public access
  path) as well as directly through QuEra's own access programs. When accessed
  via Braket, the result format follows the Braket `AHSQuantumTaskResult`
  structure; when accessed through Bloqade's native backend, the result is a
  `Report` containing per-shot atom-state configurations.
- Result semantics: each shot records the detected state (ground or Rydberg
  excited) of each atom in the register, typically as a binary per-shot sequence of
  atom states. This is structurally different from qubit bitstring measurements.
- QuEra is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the open-source
  Bloqade framework and Braket documentation. Live field population for every
  configuration or access mode was not verified through authenticated access.
