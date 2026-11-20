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

- [`amazon-braket-fixture.md`](amazon-braket-fixture.md) — fixture-specific mapping note for the Amazon Braket
  prototype fixture
- [`ibm-quantum-fixture.md`](ibm-quantum-fixture.md) — fixture-specific mapping note for the IBM Quantum prototype
  fixture
- [`ionq-fixture.md`](ionq-fixture.md) — fixture-specific mapping note for the
  IonQ prototype fixture

## Errata (2026-11-20)

A check of release dates against the 2026-07-19 cutoff found listed versions
that were not the latest stable release at the cutoff (Qiskit IBM Runtime,
Ocean SDK, Amazon Braket SDK, Perceval, and the IQM clients used by VTT QX),
and one entry (QuEra) that describes the July evidence as authenticated. Each
affected ledger keeps its July text and ends with a dated erratum:
[ibm-quantum.md](ibm-quantum.md), [d-wave.md](d-wave.md),
[amazon-braket.md](amazon-braket.md), [quera.md](quera.md),
[quandela.md](quandela.md), [vtt-qx.md](vtt-qx.md).
