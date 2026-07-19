# Provider evidence ledgers

This directory contains one evidence ledger per analyzed quantum platform.
Each ledger documents the public sources from which interface structure and
provenance attribute coverage were assessed.

## Evidence boundary (all ledgers)

All ledgers share the same evidence boundary: public documentation, public API
schemas and generated client models, maintained open-source SDK source code,
package documentation, worked examples, and release notes. No ledger claims
authenticated operational verification; interface behavior is assessed through
public artifacts only.

## Detailed profile linkage

The detailed supplementary profile is now present at
[`../provider-profiles/platform-specific-findings.md`](../provider-profiles/platform-specific-findings.md).
It links each platform section to exactly one comparative ledger in this
directory using relative Markdown links.

## Platform index

| Platform | Classification | Ledger |
|---|---|---|
| AQT (Alpine Quantum Technologies) | hardware-provider (trapped-ion) | [aqt.md](aqt.md) |
| D-Wave | hardware-provider (quantum annealing) | [d-wave.md](d-wave.md) |
| Google Quantum AI | hardware-provider (superconducting) | [google-quantum-ai.md](google-quantum-ai.md) |
| IBM Quantum | hardware-provider (superconducting) | [ibm-quantum.md](ibm-quantum.md) |
| IonQ | hardware-provider (trapped-ion) | [ionq.md](ionq.md) |
| IQM | hardware-provider (superconducting) | [iqm.md](iqm.md) |
| Pasqal | hardware-provider (neutral-atom) | [pasqal.md](pasqal.md) |
| Quandela | hardware-provider (photonic) | [quandela.md](quandela.md) |
| Quantinuum | hardware-provider (trapped-ion) | [quantinuum.md](quantinuum.md) |
| QuEra Computing | hardware-provider (neutral-atom) | [quera.md](quera.md) |
| Rigetti Computing | hardware-provider (superconducting) | [rigetti.md](rigetti.md) |
| VTT QX | hardware-provider (superconducting) | [vtt-qx.md](vtt-qx.md) |
| Amazon Braket | cloud aggregator | [amazon-braket.md](amazon-braket.md) |
| Microsoft Azure Quantum | cloud aggregator | [azure-quantum.md](azure-quantum.md) |
| qBraid | cloud aggregator | [qbraid.md](qbraid.md) |

**Total:** 15 platforms (12 hardware-provider platforms + 3 cloud aggregators).

## Fixture-specific companion notes (prototype fixtures)

The 15 full ledgers above support the comparative platform analysis. Three
shorter fixture-focused companion notes also remain for the prototype fixtures:

- [`braket.md`](braket.md) — fixture-specific mapping note for the Braket
  prototype fixture
- [`ibm.md`](ibm.md) — fixture-specific mapping note for the IBM prototype
  fixture
- [`ionq-fixture.md`](ionq-fixture.md) — fixture-specific mapping note for the
  IonQ prototype fixture
