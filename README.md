[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21451599.svg)](https://doi.org/10.5281/zenodo.21451599)
[![ci](https://github.com/qmill-org/quantum-provenance-prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/qmill-org/quantum-provenance-prototype/actions/workflows/ci.yml)

# Quantum Provenance Prototype

Reproducible research artifact for the paper:

> **Toward Standardized Quantum Provenance: A Cross-Provider Analysis, Unified
> API, and Reference Prototype**

An evidence-aware provenance contract (OpenAPI), provider adapters for Amazon
Braket, IBM Quantum, IonQ and Quandela, live retrieval layers, a reference
HTTP service, and the paper's experiments. Everything is reproducible offline
from **sanitized captures of real, purpose-run provider jobs**; no network
access or provider credentials are needed except to take new captures.

Version `0.2.0` is the revision for the reviews; `0.1.0` (the artifact as
submitted, DOI above) is unchanged. See [CHANGELOG.md](CHANGELOG.md).

| Field | Value |
| --- | --- |
| Contract / schema version | `0.2.0` (accepts `0.1.0-prototype` records; changes are additive) |
| Attribute inventory | `0.2.0` ([`artifact/attribute-inventory.json`](artifact/attribute-inventory.json)) |
| Provider-interface verification cutoff (documentation analysis) | 2026-07-19 |
| Live captures | 2026-11-18 to 2026-11-20 |
| Artifact author | Jouni Peltonen |

## Layout

```
src/qmill_quantum_provenance/
  openapi.json        # the contract (source of truth, shipped as package data)
  models.py           # record model mirroring the contract
  adapter.py          # adapter interface and shared mapping rules
  service.py          # in-process service (create / get)
  adapters/           # braket, ibm, ionq, quandela provenance adapters
  live/               # live retrieval layers, capture, sanitize, validate
  replay.py           # offline replay of a capture through the retrieval interface
  server/             # reference HTTP service (FastAPI, SQLite, API keys)
  comparison/         # baseline comparison: flat baseline, oracle, readers
  experiments/        # failure injection: transport, seam and drift stages
  evaluation.py       # attribute classification report over the evaluation captures
captures/             # sanitized live captures + findings F1-F18 (README)
runs/                 # run ledgers and programs of the purpose-run jobs
scripts/              # submission scripts for those jobs (need credentials)
protocols/            # pre-registered protocols, with results and change logs
artifact/             # committed, drift-checked outputs cited by the paper
supplementary/        # July 2026 provider evidence ledgers and profiles
tests/                # pytest suite (offline)
```

## Reproducing the results

```bash
uv sync --extra dev --extra http --extra live    # or: pip install -e ".[dev,http,live]"

uv run pytest -q                                  # offline test suite
uv run python -m qmill_quantum_provenance.evaluation --check
uv run python -m qmill_quantum_provenance.generate_examples --check

# experiments (rewrite the committed outputs; compare with git diff)
uv run python -m qmill_quantum_provenance.live.validate captures \
    --report captures/validation-v0.2.0-adapters.json
uv run python -m qmill_quantum_provenance.comparison.run \
    --output artifact/baseline-comparison.json     # needs the git tags (full clone)
uv run python -m qmill_quantum_provenance.experiments.run \
    --output artifact/failure-injection.json
```

| Output | What it holds | Protocol |
| --- | --- | --- |
| [`artifact/evaluation-results.json`](artifact/evaluation-results.json) | Every inventory attribute classified per provider for one real capture per provider path, built with the application context from the run ledgers | — |
| [`artifact/examples/`](artifact/examples) | The four corresponding provenance records | — |
| [`captures/validation-v0.2.0-adapters.json`](captures/validation-v0.2.0-adapters.json) | Every capture mapped, schema-validated and checked against what the provider returned (`validation-v0.1.0-adapters.json`: the submitted adapters, frozen) | [captures/README.md](captures/README.md) |
| [`artifact/baseline-comparison.json`](artifact/baseline-comparison.json) | Flat baseline vs `v0.1.0` vs `v0.2.0` on development and hold-out captures | [baseline-comparison.md](protocols/baseline-comparison.md) |
| [`artifact/failure-injection.json`](artifact/failure-injection.json) | Transport faults, seam faults and a real interface change | [failure-injection.md](protocols/failure-injection.md) |
| [`protocols/new-provider-quandela.md`](protocols/new-provider-quandela.md) | New-provider integration, with measures and change log | — |

Each protocol was committed before its experiment ran and records its results
before and after any fix, with the reason for every later change.

## Live captures and new jobs

Captures are taken with `python -m qmill_quantum_provenance.live.capture
<provider> <job ids> --out captures` and need provider credentials in the
environment (see `scripts/` for the submission side and `runs/` for what was
submitted). Captures are sanitized before they are written: secrets,
AWS account and IBM IAM identifiers, and credentials in free text are masked,
and program text is replaced by its SHA-256 digest and size.

The captures contain responses about the authors' own purpose-run jobs. The
synthetic, documentation-derived fixtures of `v0.1.0` remain as unit-test
fixtures under [`tests/fixtures/`](tests/fixtures).

## Reference HTTP service

A reference service (not a production deployment) serves the contract over
HTTP with SQLite persistence, API-key authentication bound to a tenant, record
versions and refresh. Scope and security tests:
[`protocols/http-service.md`](protocols/http-service.md).

```bash
uv pip install -e ".[http,dev]"

# keys.json holds only SHA-256 hashes of API keys:
python - <<'PY'
import json; from qmill_quantum_provenance.server.auth import hash_key
json.dump([{"sha256": hash_key("change-me"), "tenant": "t1",
            "permissions": ["read", "write"]}], open("keys.json", "w"))
PY

# replay mode serves the committed captures; QPROV_MODE=live uses provider
# credentials from the server environment
QPROV_KEYS_FILE=keys.json QPROV_DB=provenance.sqlite QPROV_MODE=replay \
    python -m qmill_quantum_provenance.server

curl -s -X POST localhost:8000/v1/provenance-records \
    -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
    -d '{"provider": "ibm", "external_job_id": "dbvb21eppgvc73e5o380"}'

# contract conformance against the running service
st run http://127.0.0.1:8000/v1/openapi.json -H "Authorization: Bearer change-me" \
    --checks all --mode all --max-examples 200
```

## Supplementary material

[`supplementary/provider-evidence/`](supplementary/provider-evidence) holds the
July 2026 evidence ledgers of the 15-platform documentation analysis (with
dated errata), and [`supplementary/provider-profiles/`](supplementary/provider-profiles)
the per-platform findings. [`supplementary/conceptual-api/`](supplementary/conceptual-api)
holds the conceptual API example from the paper.

## Citation

Please cite via [`CITATION.cff`](CITATION.cff). Versions are archived at
Zenodo; `0.1.0`: [10.5281/zenodo.21451599](https://doi.org/10.5281/zenodo.21451599).

## License

[MIT](LICENSE) © 2026 QMill Oy.
