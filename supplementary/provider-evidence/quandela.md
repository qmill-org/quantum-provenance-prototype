# Evidence ledger — Quandela

**Classification:** hardware-provider platform (photonic)

**Evidence boundary:** This ledger covers publicly available Quandela
documentation, the open-source Perceval photonic quantum computing framework
source code, package documentation, worked examples, and release notes. No
claim of authenticated operational verification is made; interface behavior is
assessed through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Perceval documentation | Perceval documentation 1.2 | Official documentation | https://perceval.quandela.net/docs/ | 2026-07-19 | Photonic circuit model; linear-optical components; sampling and boson-sampling result format; remote execution via Quandela cloud |
| Perceval (open source) | Perceval source release 1.2.4 | SDK source / package documentation | https://github.com/Quandela/Perceval | 2026-07-19 | `Circuit` and `Processor` objects; result `BSDistribution` (boson-sampling distribution); remote provider interface; job submission and retrieval |
| perceval-quandela PyPI releases | Perceval PyPI package at cutoff 1.2.3 | Package release page | https://pypi.org/project/perceval-quandela/ | 2026-07-19 | Published release history and version constraints |
| Quandela cloud documentation | Public documentation reviewed 2026-07-19 | Official documentation | https://cloud.quandela.com/ | 2026-07-19 | Cloud access model; available photonic processors; job management |

## Notes

- Quandela provides photonic quantum hardware where computation is performed
  using linear-optical circuits and single-photon sources. The `Perceval`
  open-source framework is both the primary circuit-description tool and the
  documented interface for remote execution on Quandela hardware.
- Result semantics are fundamentally different from qubit-based platforms:
  outcomes are described as a boson-sampling distribution (`BSDistribution`)
  mapping photon-number configurations to amplitudes or probabilities, rather
  than bitstring counts. This distinction is significant for the unified
  provenance model's result representation.
- The Perceval framework supports both local simulation and remote execution
  on Quandela hardware through a `RemoteProcessor` interface; the remote
  interface is authenticated and its exact field structure beyond what is
  documented in the open-source library could not be independently verified.
- Quandela is not among the three providers with prototype fixtures in this
  repository; its inclusion in the comparative analysis is based on public
  documentation and open-source SDK evidence only.
- The documented interface structure is established through the open-source
  Perceval framework. Live field population and result structure for every
  device configuration or account type was not verified through authenticated
  access.
