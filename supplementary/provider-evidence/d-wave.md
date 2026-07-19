# Evidence ledger — D-Wave

**Classification:** hardware-provider platform (quantum annealing)

**Evidence boundary:** This ledger covers publicly available D-Wave
documentation, maintained open-source Ocean SDK source code and package
documentation, worked examples, release notes, and the public D-Wave Leap
service documentation. No claim of authenticated operational verification is
made; interface behavior is assessed through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| D-Wave documentation portal | Current public release | Official documentation | https://docs.dwavesys.com/ | 2026-07-19 | Quantum annealing computation model; QPU topology; problem submission; solution structure |
| D-Wave Ocean SDK documentation | Current public release | Official documentation | https://docs.ocean.dwavesys.com/ | 2026-07-19 | Problem formulation (QUBO/BQM/CQM); sampler interfaces; result `SampleSet` format; timing data |
| dwave-ocean-sdk (open source) | latest stable release | SDK source / package documentation | https://github.com/dwavesystems/dwave-ocean-sdk | 2026-07-19 | Meta-package encompassing Ocean toolchain; release history |
| dwave-cloud-client (open source) | latest stable release | SDK source / package documentation | https://github.com/dwavesystems/dwave-cloud-client | 2026-07-19 | Leap API client; solver listing; problem submission; `Future` result object fields (`timing`, `num_occurrences`, `energy`, `sample`) |
| dwave-cloud-client PyPI releases | latest stable | Package release page | https://pypi.org/project/dwave-cloud-client/ | 2026-07-19 | Published release history and version constraints |
| D-Wave Leap service documentation | Current public release | Official documentation | https://docs.dwavesys.com/docs/latest/c_leap.html | 2026-07-19 | Cloud service access model; solver types available (QPU, hybrid); access tiers |

## Notes

- D-Wave is a quantum-annealing hardware provider: its computational model
  (QUBO/BQM/CQM → sampler → SampleSet) differs fundamentally from gate-based
  platforms. Provenance attributes common to gate-model platforms (circuit,
  qubit characterization, gate fidelities) are not applicable; energy,
  annealing schedule, and chain-break fraction are the relevant problem-specific
  fields.
- The `SampleSet` result object documents fields including `sample` (variable
  assignments), `energy`, `num_occurrences`, `timing`, and solver-specific
  metadata such as `chain_break_fraction`.
- Annealing timing data (`timing` dict with `qpu_sampling_time`,
  `qpu_anneal_time_per_sample`, etc.) is documented in the SDK and developer
  guide.
- Hardware characterization (coupler weights, qubit connectivity) is documented
  via the solver graph, but dynamic calibration snapshots comparable to
  gate-model providers are not part of the public result interface.
- D-Wave is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the open-source
  Ocean SDK. Live field population for every problem type, solver, or account
  tier was not verified through authenticated access.
