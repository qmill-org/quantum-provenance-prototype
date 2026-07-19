# Evidence ledger — VTT QX

**Classification:** hardware-provider platform (superconducting)

**Evidence boundary:** This ledger covers publicly available VTT Technical
Research Centre of Finland documentation for its quantum computing services,
and the IQM client SDK documentation relevant to VTT QX systems (which use IQM
hardware). Access to VTT QX systems requires a separate access agreement with
VTT; the interface is assessed through public documentation and the IQM
open-source client. No claim of authenticated operational verification is made.

**Verification date:** 2026-07-19 — sources listed below were confirmed
accessible and reviewed against the repository evaluation cutoff of July 2026.

## Evidence table

| Resource | Assessed version/interface | Evidence type | Official stable URL | Accessed/verified | Claims supported |
|---|---|---|---|---|---|
| VTT quantum technology overview | Current public pages | Official documentation | https://www.vttresearch.com/en/ourservices/quantum-technology | 2026-07-19 | Platform overview; VTT 5-qubit and 20-qubit systems; research access model |
| VTT Q5sim / VTT QX service information | Current public pages | Official documentation | https://www.vttresearch.com/en/ourservices/quantum-technology | 2026-07-19 | System naming (Q5sim evolved to VTT QX); hardware specifications; access arrangements |
| IQM client SDK (open source) — applicable to VTT QX | latest stable release | SDK source / package documentation | https://github.com/iqm-finland/iqm-client | 2026-07-19 | REST API client interface applicable to IQM-hardware systems including VTT QX; `RunRequest` and `RunResult` field structure |
| IQM documentation (applicable interface) | Current public release | Official documentation | https://docs.meetiqm.com/ | 2026-07-19 | IQM server REST API; measurement result structure; job status |

## Notes

- VTT QX systems use IQM superconducting hardware and are accessed through the
  IQM REST API interface. The programmatic interface is therefore the same as
  documented in the IQM evidence ledger (`iqm.md`); the VTT QX ledger covers
  the platform-specific access model and naming.
- Public documentation specifically dedicated to the VTT QX programmatic
  interface is limited. The primary public evidence sources are the VTT website
  (describing the hardware and access model) and the IQM client SDK (describing
  the REST interface applicable to all IQM-based systems).
- Access to VTT QX requires a separate access agreement with VTT; the system
  is not publicly accessible through a self-service cloud portal. Accordingly,
  provenance completeness can only be assessed through the documented IQM
  interface and public VTT information.
- A precise stable URL for VTT QX-specific API documentation or an OpenAPI
  specification could not be independently verified; the official VTT website
  root URL is used as the evidence source for platform identity and access model.
- The documented interface structure applicable to VTT QX is established
  through the IQM open-source client. Live field population for VTT QX-specific
  configurations was not verified through authenticated access.
