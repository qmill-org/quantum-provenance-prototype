# Quantum Provenance Prototype

Reproducible research artifact for the paper:

> **Toward Standardized Quantum Provenance: A Cross-Provider Analysis, Unified
> API, and Reference Prototype**

This repository contains the self-contained reference prototype and evaluation
harness for a unified quantum-provenance model spanning three provider
platforms (Amazon Braket, IBM Quantum, IonQ). It reproduces the paper's
evaluation entirely from sanitized, checked-in fixtures — **no network access,
credentials, or provider SDKs are required**.

The package (`qmill_quantum_provenance`) is a standalone extraction of the
prototype; it does not depend on any private QMill code.

## Provenance of this artifact

| Field | Value |
| --- | --- |
| Paper | *Toward Standardized Quantum Provenance: A Cross-Provider Analysis, Unified API, and Reference Prototype* |
| Author | Jouni Peltonen |
| Prototype evaluation cutoff date | 2026-07-17 |
| Provider-interface verification cutoff date | 2026-07-19 |
| Schema version | `0.1.0-prototype` |
| Report format | `qmill.provenance.evaluation` v`0.2.0` |

## Layout

```
src/qmill_quantum_provenance/   # the prototype package
  models.py         # canonical provenance domain model (mirrors the OpenAPI contract)
  adapter.py        # provenance adapter interface + request/context dataclasses
  registry.py       # provider -> adapter registry
  service.py        # create_record / get_provenance service operations
  contract.py       # loads openapi.json, validates records against the schema
  redaction.py      # secret/PII redaction applied before records are emitted
  replay.py         # offline ProviderAdapter that replays a captured fixture
  integration.py    # inlined minimal provider-integration interface (see above)
  evaluation.py     # reproducible evaluation harness (metrics + experiments)
  generate_examples.py  # regenerates the canonical example records
  adapters/{braket,ibm,ionq}.py  # per-provider provenance adapters
  openapi.json      # canonical contract (source of truth, shipped as package data)
tests/              # pytest suite + sanitized fixtures
artifact/           # committed, drift-checked evaluation outputs (paper values)
supplementary/      # narrative supplementary material for the paper
```

## Requirements

- Python 3.12 (>=3.12,<3.14)
- The only runtime dependency is `jsonschema>=4.0`.

## Reproducing the evaluation

```bash
# 1. Create an isolated environment and install the package
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Run the test suite (34 tests, no network/credentials)
pytest tests/

# 3. Verify the committed evaluation report is reproducible (exits non-zero on drift)
python -m qmill_quantum_provenance.evaluation --check

# 4. Verify the committed example records are reproducible
python -m qmill_quantum_provenance.generate_examples --check
```

`pip` may be used instead of `uv` throughout.

### Regenerating outputs

```bash
# Rewrite the evaluation report in place
python -m qmill_quantum_provenance.evaluation --output artifact/evaluation-results.json

# Rewrite the example provenance records in place
python -m qmill_quantum_provenance.generate_examples
```

## Expected output

- **Tests:** `34 passed`.
- **`--check` commands:** both print an "up to date" message and exit `0`.

The committed evaluation report ([`artifact/evaluation-results.json`](artifact/evaluation-results.json))
records the headline metrics per provider (handwritten adapter lines of code and
evidence-category counts):

| Provider | Adapter LOC | Evidence attributes |
| --- | --- | --- |
| Braket | 428 | 25 |
| IBM | 486 | 27 |
| IonQ | 526 | 16 |

Shared, provider-independent implementation: **861** lines. No inventory
attribute is left `unclassified` for any provider. The report also contains
three runnable experiments (schema-change backward compatibility, provider-input
isolation, and partial-record graceful degradation).

## Synthetic fixtures and public provider evidence

The prototype runs against **sanitized, synthetic fixtures** under
[`tests/fixtures/`](tests/fixtures), one `completed.json` (and a
`completed_no_calibration.json` for the partial-record experiment) per provider.
These fixtures are hand-authored, structurally faithful representations of the
kind of job records each provider platform returns:

- **Shape and field semantics** mirror each provider's public result / device
  schemas (Amazon Braket task + device calibration, IBM Quantum job + backend
  properties, IonQ job histogram + characterization). The mapping from public
  provider evidence to the fixture fields is documented in
  [`supplementary/provider-profiles/`](supplementary/provider-profiles) and
  [`supplementary/provider-evidence/`](supplementary/provider-evidence).
- **All secrets and account-specific identifiers are placeholders.** Fixtures
  use synthetic values (e.g. `FAKE-*` markers, example ARNs/IDs). The redaction
  layer ([`redaction.py`](src/qmill_quantum_provenance/redaction.py)) and its
  tests assert that no such material ever reaches an emitted record.
- **No proprietary or exported provider data is included.** The fixtures are
  independent reconstructions from public documentation, not captures of real
  jobs. This keeps the artifact freely redistributable and deterministic.

A complete, human-readable example of a fully populated provenance response is
provided in
[`supplementary/complete-example-provenance-response.json`](supplementary/complete-example-provenance-response.json).
Supplementary conceptual and comparative materials are also available under
[`supplementary/conceptual-api/`](supplementary/conceptual-api/) and
[`supplementary/provider-profiles/platform-specific-findings.md`](supplementary/provider-profiles/platform-specific-findings.md).

## Citation

If you use this artifact, please cite it via [`CITATION.cff`](CITATION.cff).
A versioned release of this repository will be archived on Zenodo. Until a DOI
is available, cite the artifact using [`CITATION.cff`](CITATION.cff).

## License

[MIT](LICENSE) © 2026 Jouni Peltonen.
