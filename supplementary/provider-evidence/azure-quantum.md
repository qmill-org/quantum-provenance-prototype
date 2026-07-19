# Evidence ledger — Microsoft Azure Quantum

**Classification:** cloud aggregator

**Evidence boundary:** This ledger covers publicly available Azure Quantum
documentation, the Microsoft Learn portal, maintained open-source Azure Quantum
Development Kit (QDK) and azure-quantum Python SDK source code, package
documentation, worked examples, and release notes. No claim of authenticated
operational verification is made; interface behavior is assessed through public
artifacts only.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| Azure Quantum documentation | Current public release | Official documentation | https://learn.microsoft.com/en-us/azure/quantum/ | 2026-07-19 | Platform overview; supported hardware providers (IonQ, Quantinuum, Rigetti, and others); job submission workflow; result retrieval |
| Azure Quantum Python SDK (azure-quantum) documentation | Current public release | Official documentation | https://learn.microsoft.com/en-us/azure/quantum/install-overview-qdk | 2026-07-19 | SDK installation; workspace connection; job submission; result download |
| qdk-python (open source) | latest stable release | SDK source / package documentation | https://github.com/microsoft/qdk-python | 2026-07-19 | `Workspace` and `Job` objects; `Job.get_results()` method; job status and metadata fields; provider-specific output format handling |
| azure-quantum PyPI releases | latest stable | Package release page | https://pypi.org/project/azure-quantum/ | 2026-07-19 | Published release history and version constraints |
| Azure Quantum REST API reference | Current public release | API reference | https://learn.microsoft.com/en-us/rest/api/azurequantum/ | 2026-07-19 | Job resource fields (`id`, `name`, `status`, `createdTime`, `endTime`, `target`, `outputDataUri`); workspace and provider configuration |

## Notes

- Azure Quantum is a **cloud aggregator**: it provides access to hardware from
  multiple independent hardware providers (including IonQ, Quantinuum, Rigetti,
  and others) through a common Azure subscription, workspace, and job-management
  interface.
- The Azure Quantum REST API and `azure-quantum` SDK provide a uniform job
  abstraction across providers; however, the result payload structure is
  provider-specific and is returned as a raw blob or provider-formatted file
  that must be parsed according to the target provider's schema.
- This means that provenance completeness for any given target depends on both
  the Azure job metadata (provider-neutral) and the embedded provider result
  (provider-specific). The aggregator adds a layer of indirection similar to
  Amazon Braket.
- Azure Quantum also supports quantum-inspired optimization solvers and Q#
  simulation; these are not gate-model quantum hardware execution paths and
  are outside the scope of this comparative analysis.
- The documented interface structure is established through the public REST API
  reference and open-source azure-quantum SDK. Live field population for every
  provider target, region, or account configuration was not verified through
  authenticated access.
