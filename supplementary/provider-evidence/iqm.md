# Evidence ledger — IQM

**Classification:** hardware-provider platform (superconducting)

**Evidence boundary:** This ledger covers publicly available IQM documentation,
maintained open-source IQM client SDK and Qiskit-on-IQM extension source code,
package documentation, worked examples, and release notes. No claim of
authenticated operational verification is made; interface behavior is assessed
through public artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| IQM documentation portal | No exact assessed version established in paper/profile (public release reviewed 2026-07-19) | Official documentation | https://docs.meetiqm.com/ | 2026-07-19 | Platform overview; hardware systems; job submission workflow; result format |
| iqm-client (open source) | No exact assessed version established in paper/profile (latest stable release reviewed 2026-07-19) | SDK source / package documentation | https://github.com/iqm-finland/iqm-client | 2026-07-19 | REST API client for IQM servers; job submission (`RunRequest`); result retrieval (`RunResult`); circuit model (`IQMCircuit`); status fields |
| iqm-client PyPI releases | No exact assessed version established in paper/profile (latest stable release reviewed 2026-07-19) | Package release page | https://pypi.org/project/iqm-client/ | 2026-07-19 | Published release history and version constraints |
| qiskit-on-iqm (open source) | No exact assessed version established in paper/profile (latest stable release reviewed 2026-07-19) | SDK source / package documentation | https://github.com/iqm-finland/qiskit-on-iqm | 2026-07-19 | Qiskit backend adapter; result conversion to Qiskit `Result` format; backend properties |
| qiskit-on-iqm PyPI releases | No exact assessed version established in paper/profile (latest stable release reviewed 2026-07-19) | Package release page | https://pypi.org/project/qiskit-on-iqm/ | 2026-07-19 | Published release history and version constraints |
| IQM REST API (OpenAPI) | Current server version | API reference / OpenAPI specification | https://docs.meetiqm.com/ | 2026-07-19 | Job submission and retrieval endpoints; `RunResult` fields including measurement outcomes (per-qubit binary arrays per shot); metadata fields |

## Notes

- IQM provides a publicly documented REST API for authenticated access to its
  quantum computing servers. The `iqm-client` open-source Python package
  implements this REST interface and is the primary evidence source for the
  programmatic interface structure.
- The `RunResult` response documents measurement outcomes as a dictionary of
  measurement key to list-of-lists (shots × qubits binary values), structurally
  similar to Cirq's measurement array model.
- IQM is notable in the comparative analysis as a hardware provider with a
  publicly documented authenticated REST interface: the API endpoints, request
  and response schemas, and authentication mechanism are described in public
  documentation and the open-source client, even though access requires
  credentials.
- IQM systems are also accessible through certain aggregator platforms (e.g.
  Amazon Braket in some regions); those access paths are covered under the
  respective aggregator ledgers.
- VTT QX systems use IQM hardware and are accessed through the IQM interface;
  see the VTT QX ledger for that platform's specific documentation boundary.
- The documented interface structure (request/response schemas, field semantics)
  is established through the open-source client and official documentation.
  Live field population for every system, job configuration, or account type
  was not verified through authenticated access.
