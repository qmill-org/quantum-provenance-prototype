# Detailed Platform-Specific Quantum Provenance Findings

## Purpose and scope

This supplementary document contains the detailed platform profiles supporting
the comparative provenance analysis in the accompanying paper:

> *Toward Standardized Quantum Provenance: A Cross-Provider Analysis, Unified
> API, and Reference Prototype*

The main paper contains condensed platform summaries and the comparative
coverage matrix. This document retains the fuller evidence-based rationale
behind the platform classifications.

The analysis concerns provenance capabilities documented through publicly
accessible:

- official SDK and API documentation;
- public OpenAPI specifications and generated client models;
- maintained SDK source code and package documentation;
- provider examples, tutorials, release notes, and public schemas; and
- relevant technical and peer-reviewed literature.

The study did not authenticate to deployed provider services or submit jobs
solely for the comparative analysis. Consequently, the findings establish
documented resource structures and programmatic operations but do not prove
that every documented field is populated for every account, device, region, or
completed job.

The final verification cutoff was **July 19, 2026**. SDK and API versions refer to
the versions assessed at that cutoff unless otherwise noted.

## Interpretation of platform categories

A **hardware-provider platform** is operated by, or primarily represents access
to, one hardware provider's systems. A provider-neutral SDK does not make a
service an aggregator when its adapters connect independently to each
provider's own service.

A **cloud aggregator** provides access to hardware from multiple independent
providers through a common account, job-management model, and execution
interface.

For aggregators, the assessment distinguishes:

- metadata normalized into the common aggregator model;
- metadata passed through from an underlying provider; and
- provider-specific information not consistently available across connected
  hardware.

Rich provenance for one connected device does not by itself establish
comprehensive aggregator-level coverage.

---

# Hardware-Provider Platforms

## AQT

### Assessed interfaces

- AQT Arnica platform
- Qiskit AQT Provider 1.15.0
- AQT Public API 1.1.1
- OpenAPI 3.1 specification

### Findings

AQT provides authenticated cloud access to its trapped-ion systems through the
Arnica platform, the Qiskit AQT Provider, and the AQT Public API. The API
exposes resource characterization including per-qubit single-qubit gate
fidelities, mean two-qubit gate fidelity, SPAM fidelity, T1 and T2 coherence
times, gate and readout durations, and the timestamp of the latest
characterization update. Resource metadata also identify the available number
of qubits, while AQT's trapped-ion architecture provides all-to-all
connectivity.

Circuit and compilation provenance are strongest on the client side. The
Qiskit provider exposes the original and transpiled circuits, the native `rz`,
`r`, and `rxx` gate set, configurable optimization levels, and AQT-specific
transpiler passes. These artifacts can be inspected before submission, but
compilation configuration, random seeds, timing, and transpiler decisions are
not systematically returned with the completed job.

The API provides job submission, status, identifiers, shot-controlled
execution, and result samples, but the public documentation does not establish
comprehensive queue and execution timing or intermediate-result provenance.
Software and access versions can be recorded by the client, but they are not
provided as a standardized access-context record for each execution.

### Assessment summary

AQT documents comprehensive current QPU characterization and useful execution
support. Circuit, compilation, and software-access provenance remain partly
dependent on application-side capture.

### Evidence references

See the [AQT evidence ledger](../provider-evidence/aqt.md).

---

## D-Wave

### Assessed interfaces

- D-Wave Leap
- Ocean SDK 9.3.0
- Solver Application Programming Interface
- Region-specific `/sapi/v2` service
- Version-3 solver resource representations

### Findings

D-Wave provides authenticated access to quantum annealers and hybrid solvers
through Leap, Ocean, and the Solver Application Programming Interface. The
current solver representations identify a QPU through its solver name and
`graph_id`. The graph identifier is important for provenance because it
distinguishes changes to the active QPU working graph without relying solely on
changes to the solver name.

D-Wave exposes extensive annealer-specific device information through solver
properties, including:

- active qubits and couplers;
- topology;
- supported problem types;
- bias and coupling ranges;
- annealing-time ranges;
- anneal-offset ranges;
- supported annealing schedules; and
- problem-timing model data.

These attributes do not map directly to gate-model concepts such as native
circuit gates or T1 and T2 coherence times. They provide the corresponding
hardware context required for reproducing quantum-annealing experiments and
should therefore be represented through technology-specific extensions rather
than treated as missing gate-model attributes.

Compilation provenance corresponds primarily to minor embedding, which maps
logical variables to physical qubits and chains. Ocean can retain the
embedding, chain strength, chain-break method, embedding parameters, and
embedding and unembedding timing in `SampleSet` metadata. This capture is
optional and must be explicitly enabled. The service does not retain a
standardized history of all preprocessing and embedding decisions.

Execution provenance is comparatively strong. Public interfaces document
problem identifiers, solver and working-graph identity, status, submission and
completion timestamps, samples, energies, occurrence counts, and detailed QPU
timing. Software and access versions remain application-captured rather than
being returned as a unified access-context record.

### Assessment summary

D-Wave documents comprehensive applicable QPU and execution provenance.
Logical-problem representation, embedding provenance, and software-access
context require technology-specific mapping and, in some cases, explicit
client-side capture.

### Evidence references

See the [D-Wave evidence ledger](../provider-evidence/d-wave.md).

---

## Google Quantum AI

### Assessed interfaces

- Google Quantum Computing Service
- Cirq 1.7.0
- Quantum Engine API
- Authorized Google Cloud project resources

### Findings

Google Quantum AI provides restricted, authenticated access to its
superconducting processors through Google Quantum Computing Service, Cirq, and
the Quantum Engine API. Although Cirq contains integrations for third-party
platforms, these integrations connect to the providers' respective services
rather than routing execution through Google Quantum Computing Service.
Google Quantum AI is therefore classified as a hardware-provider platform
rather than a cloud aggregator.

Quantum Engine documents comprehensive circuit provenance through persistent
program resources. Submitted single- and multi-circuit programs can be
retrieved and deserialized into Cirq circuits. Associated job resources retain
parameter sweeps, repetition counts, descriptions, labels, and program–job
identifiers. Historical programs, jobs, and results remain retrievable within
the originating Google Cloud project.

Device and calibration provenance are also comprehensive. Processor
specifications describe physical qubits, connectivity, supported gates, and
operation constraints. Processor configurations combine an effective device
specification with characterization metrics and can be identified through an
automation-run name or immutable configuration-snapshot identifier.

Quantum Engine documents current and historical calibrations, including
timestamped, qubit-specific, and qubit-pair-specific metrics such as:

- T1;
- readout errors;
- single-qubit randomized-benchmarking errors; and
- two-qubit cross-entropy-benchmarking errors.

A completed job can reference the calibration recorded at execution time and
the processor configuration used for the job.

Compilation provenance remains partial. Cirq allows users to inspect
device-targeted transformations, qubit placement, routing, target gatesets,
optimization, and optional workflow-level random seeds. The transformed circuit
can be submitted and retained as the Engine program, but the service does not
return a complete pass history, intermediate circuits, compilation timing,
compiler version, or all client-side transformation settings.

Execution provenance includes program, job, project, and processor identifiers,
lifecycle state, creation and update timestamps, execution start and completion
timestamps, failures, results, repetitions, sweeps, calibration association,
and device-configuration identity. Exact local software versions, access
method, retrieval timestamp, and field-level availability metadata must still
be captured by the application.

### Assessment summary

Google Quantum AI documents comprehensive circuit, QPU, and execution
provenance. Detailed compilation history and standardized software-access
context remain partial.

### Evidence references

See the [Google Quantum AI evidence ledger](../provider-evidence/google-quantum-ai.md).

---

## IBM Quantum

### Assessed interfaces

- Qiskit SDK 2.5.0
- Qiskit IBM Runtime 0.47.0
- Qiskit Runtime REST API 2026-04-15

### Findings

IBM provides one of the more comprehensive documented provenance footprints in
the analyzed ecosystem. Backend configuration and properties expose topology,
supported instructions, coherence metrics, gate errors and durations, and
readout errors.

Job details, metrics, and result resources provide:

- job identifiers;
- lifecycle state;
- submitted parameters;
- execution timestamps;
- QPU usage;
- result data; and
- software metadata associated with execution.

Jobs can include a `calibration_id`, while the Runtime client can retrieve
backend properties associated with the approximate time at which a job began
execution. The temporal association of such properties should nevertheless be
represented conservatively unless the provider explicitly links the snapshot
to the execution.

Circuit and compilation provenance remain less complete. Submitted inputs may
be retrievable, but post-transpilation circuits, transpiler history,
optimization decisions, and random seeds are not automatically retained as job
provenance. These fields generally require correlation with application-side
records.

### Assessment summary

IBM documents strong QPU and execution provenance but still requires
correlation across multiple resources and client-side capture of compilation
context.

Further details on the mapping challenge and the corresponding reference
prototype are provided in the main paper.

### Evidence references

See the [IBM Quantum evidence ledger](../provider-evidence/ibm-quantum.md).

---

## IonQ

### Assessed interfaces

- IonQ Quantum Cloud
- Qiskit IonQ Provider 1.1.1
- IonQ Quantum Cloud API v0.4

### Findings

IonQ provides authenticated access to its trapped-ion systems through IonQ
Quantum Cloud, its Qiskit provider, and its cloud API. The documented API
exposes current backend information and historical characterization records,
including:

- qubit count;
- connectivity;
- supported QIS and native gates;
- SPAM fidelity;
- T1 and T2 coherence information;
- gate and readout timing;
- backend status;
- average queue time; and
- characterization timestamps.

The backend response links to the latest characterization, although the public
job response does not clearly establish which historical characterization was
in force for a particular execution.

Circuit provenance is comprehensive on the client side, where the original and
locally transpiled circuits can be retained. The API accepts complete QIS or
hardware-native circuit representations, but the documented post-submission
job response provides circuit statistics and gate counts rather than returning
the complete submitted circuit.

Compilation provenance is partial but improving. API v0.4 defines
`settings.compilation` and `output.compilation` structures for compilation
settings and diagnostic output. Error-mitigation variants can include physical
`qubit_map` values. Developers can alternatively submit hardware-native
circuits and retain the exact compiled representation on the client. Compiler
versions, complete optimization history, random seeds, and compilation timing
are not systematically documented.

Execution provenance is extensive. Job records document:

- job, backend, and project identifiers;
- lifecycle status;
- submission, start, and completion timestamps;
- predicted wait and execution durations;
- actual execution duration;
- shot count;
- qubit and gate-count statistics;
- failure information;
- mitigation settings;
- result artifacts; and
- predicted or billed quantum-compute time.

IonQ result resources may contain probability histograms rather than observed
per-shot integer counts. A normalized provenance representation must preserve
these probabilities and identify any reconstructed count representation as
derived.

Software and client versions are not automatically attached to the job record.
Retrieval time and field-level availability metadata must also be captured by
the consuming application.

### Assessment summary

IonQ documents comprehensive QPU and execution provenance. Circuit persistence,
compilation detail, and standardized software-access context remain partial.

### Evidence references

See the [IonQ evidence ledger](../provider-evidence/ionq.md).

---

## IQM

### Assessed interfaces

- IQM Resonance
- IQM Client 34.0.4
- Public IQM Client data models
- Qiskit and Cirq integrations
- Documented IQM Server REST interface

### Findings

IQM provides authenticated access to superconducting quantum computers through
Resonance and IQM Client. The public client package includes Qiskit and Cirq
adapters and communicates with IQM Server through a REST interface.

The public models document static and dynamic quantum architectures, including:

- qubits;
- computational resonators;
- native operations;
- valid operation loci; and
- the calibration-set identifier from which a dynamic architecture was
  derived.

The documented client interface also defines operations for retrieving
calibration sets and associated quality-metric sets, supporting
calibration-aware transpilation and device-characterization inspection.
However, the underlying server client is documented as an unstable private
interface, and resource availability may vary between deployments.

Circuit and execution provenance are comparatively comprehensive in the
publicly documented models. The submitted job payload can be retrieved
separately and contains the circuit batch and execution parameters, including
the qubit mapping, shot count, compilation options, and requested calibration
set.

Result artifacts provide measurements and measurement counts. Job metadata
include status, errors, informational messages, and a timestamped processing
timeline. The documented job states distinguish:

- validation;
- calibration retrieval;
- compilation;
- queueing;
- hardware execution;
- post-processing; and
- completion.

This allows the durations of documented processing stages to be derived.

Compilation provenance remains partial. Client-side Qiskit and Cirq
integrations allow the final routed or decomposed circuit to be inspected
before submission. The submitted payload preserves the selected qubit mapping,
calibration-set identifier, and compilation-related options. Job metadata also
distinguish the beginning and end of server-side compilation.

The public models do not define a complete provenance record for compiler-pass
history, optimization objectives, random seeds, or generated instruction
schedules. Local software versions, retrieval timestamps, and field-level
availability metadata must be captured by the consuming application.

### Assessment summary

IQM documents broad circuit, device, and execution provenance. Its principal
limitations concern detailed compilation history and standardized
software-access metadata.

This assessment is based on public IQM Client documentation and data models.
The study did not authenticate to a deployed IQM Server. Deployment-specific
field population, retention, authorization, and backend variation were
therefore not operationally verified.

### Evidence references

See the [IQM evidence ledger](../provider-evidence/iqm.md).

---

## Pasqal

### Assessed interfaces

- Pulser 1.8.0
- `pasqal-cloud` client 0.23.0
- Pasqal Cloud REST API
- OpenAPI 3.0.2 specification

### Findings

Pasqal provides access to its neutral-atom platform through Pulser,
`pasqal-cloud`, and an authenticated cloud API. Pulser provides a detailed
pulse-level program representation containing:

- the atom register;
- the selected device;
- ordered instructions;
- addressing channels;
- pulse waveforms and durations; and
- measurement configuration.

Pasqal Cloud accepts serialized Pulser sequences at batch or job level and
returns the built sequence in the job record, allowing the submitted program
to be retrieved after execution.

Device specifications expose target constraints and capabilities, including:

- maximum atom count;
- array-geometry constraints;
- Rydberg level and interaction parameters;
- available pulse channels;
- supported states and bases;
- maximum sequence duration;
- run limits; and
- pre-calibrated register layouts.

The cloud interface also documents available devices, queue information, and
device-status history. The public interface does not provide detailed
time-varying telemetry such as per-atom coherence, operation fidelity,
preparation and measurement errors, or historical calibration snapshots.
Pre-calibrated layouts describe usable configurations but do not constitute
complete calibration provenance.

Compilation provenance is partial. Pulser preserves the selected register,
trap layout, device constraints, and hardware-compatible pulse sequence. The
cloud record includes the built sequence and variable assignments. Optimization
objectives, random seeds, transformation history, layout-generation details,
compilation timing, and compiler versions are not returned as a standardized
record.

Execution provenance is stronger. Job resources include identifiers, lifecycle
status, run count, creation, start and end timestamps, project and batch
context, progress, errors, optional logs, the built sequence, and links to final
results. Software versions and access methods can be identified but are not
automatically attached to every job in one access-context record.

### Assessment summary

Pasqal documents comprehensive execution provenance and detailed pulse-program
and device-capability information. Dynamic calibration, compilation history,
and standardized software-access metadata remain partial.

### Evidence references

See the [Pasqal evidence ledger](../provider-evidence/pasqal.md).

---

## Quandela

### Assessed interfaces

- Quandela Cloud
- Perceval 1.2 documentation
- Perceval 1.2.4 source release
- Perceval 1.2.3 PyPI release at verification cutoff
- `RemoteProcessor`
- Quandela cloud-session interface

### Findings

Quandela provides authenticated access to discrete-variable photonic quantum
processors through Quandela Cloud and Perceval. Perceval identifies Quandela
as its default cloud provider and exposes Belenos as a remote hardware target.

Perceval represents a photonic workload as an `Experiment` containing:

- the optical circuit;
- the input photon state;
- spatial modes;
- component parameters;
- logical encoding;
- heralded modes;
- detectors;
- post-selection rules; and
- measurement filters.

Experiments are serializable and included in remote-job payloads, providing
detailed client-side program provenance. Persistent retrieval of the complete
submitted experiment from a resumed cloud job was not confirmed, so the
application should retain the serialized input independently.

Remote platform specifications expose:

- hardware architecture;
- optical components;
- detector information;
- supported commands;
- photon- and mode-count constraints;
- platform parameters;
- software versions; and
- current performance characterization.

Performance data can be translated into photonic noise parameters such as
transmission, photon indistinguishability, and multiphoton emission where
supplied. The public interface does not establish immutable calibration
identifiers, historical characterization retrieval, or automatic association
of every job with a time-specific characterization snapshot.

Compilation provenance is partial. Perceval exposes client-side decomposition,
mode mapping, logical encoding, architecture validation, and compilation
parameters, including compilation seeds for supported workflows. Complete
transformation history, intermediate compiled experiments, compiler-pass
details, and compilation timing are not retained as standardized cloud-job
provenance.

Execution provenance is stronger. Remote jobs expose identifiers, status,
progress, creation and start timestamps, duration, failure details,
cancellation, result retrieval, and physical, logical, and global performance
measures where available. Platform and software versions are partly exposed,
but local dependencies, retrieval timestamps, API versions, and field-level
availability metadata require application-side capture.

### Assessment summary

Quandela documents comprehensive execution provenance and detailed
photonic-program and platform information. Persistent input association,
calibration history, compilation details, and standardized access context
remain partial.

### Evidence references

See the [Quandela evidence ledger](../provider-evidence/quandela.md).

---

## Quantinuum

### Assessed interfaces

- Quantinuum Nexus
- `qnexus` 0.46.0
- Nexus HTTP API
- Official Nexus OpenAPI schema
- TKET compilation toolkit

### Findings

Quantinuum provides authenticated access to trapped-ion systems through Nexus
and its client and HTTP API. The legacy Quantinuum job-submission API was
retired after March 31, 2026, and current remote hardware workflows use Nexus.
TKET remains the principal circuit and compilation toolkit.

Nexus provides strong circuit and compilation provenance. Input circuits are
stored as independently retrievable resources. Compilation is represented as a
first-class `CompileJob`. Compilation results retain input and compiled output
circuits and expose the applied compilation passes. When intermediate-result
storage is enabled, Nexus also preserves intermediate circuits and pass
sequences.

Backend configuration records the target system, optimization level, and
Quantinuum-specific compiler options. Random seeds, exact server-side compiler
versions, and some hardware-compiler decisions are not consistently included.
Nevertheless, Nexus retains substantially more compilation provenance than
most other provider interfaces analyzed.

Device metadata are available through stored `BackendInfo` resources,
including device identity, architecture, supported gate set, backend version,
and gate and readout error information. Execution results can retain the
backend-information snapshot associated with the job. The public interface
does not provide a complete per-job calibration snapshot containing all
time-varying coherence, duration, and calibration data.

Execution provenance is comprehensive. Nexus stores:

- job and project identifiers;
- input circuits;
- shot counts;
- backend configuration;
- results;
- backend snapshots;
- lifecycle status;
- error information;
- queue position;
- cost; and
- queued, submitted, running, and completed timestamps.

Software and access versions remain only partly captured. Local package
versions, retrieval timestamps, and field-level availability metadata are not
returned as one standardized access-context record.

### Assessment summary

Quantinuum Nexus documents comprehensive circuit, compilation, and execution
provenance. Detailed time-specific calibration and standardized software-access
metadata remain partial.

### Evidence references

See the [Quantinuum evidence ledger](../provider-evidence/quantinuum.md).

---

## QuEra through Amazon Braket

### Assessed interfaces

- QuEra Aquila
- Amazon Braket SDK 1.123.0
- Amazon Braket API
- Analog Hamiltonian Simulation schema

### Findings

QuEra provides public cloud access to Aquila through Amazon Braket. QuEra
programs use Braket's Analog Hamiltonian Simulation schema rather than a
gate-based circuit.

An Analog Hamiltonian Simulation program specifies physical atom-register
coordinates and time- and space-dependent driving fields, including:

- amplitude;
- phase;
- global detuning; and
- optional local detuning.

The complete submitted action is retained in task-result metadata with its
schema version, providing comprehensive applicable program provenance.

Device capabilities expose:

- the supported Analog Hamiltonian Simulation representation;
- atom-count and register-geometry constraints;
- coordinate and time resolution;
- Rydberg interaction parameters;
- global- and local-field constraints;
- execution windows;
- shot limits;
- device status; and
- an update timestamp.

Braket also provides calibration information through Aquila device properties.
The public interface does not clearly associate each task with an immutable
calibration identifier or historical calibration snapshot. Detailed
time-specific preparation, measurement, and coherence metrics are not
systematically retained with every execution.

Compilation mainly consists of validating and discretizing an Analog
Hamiltonian Simulation program against Aquila's constraints. The
device-compatible action can be inspected before submission and is retained in
the result. The original pre-discretization program, individual transformation
decisions, compiler version, random seeds, and compilation duration are not
returned as a complete history.

Execution resources include task and device identifiers, shots, lifecycle
status, creation and completion timestamps, queue information, failure details,
enabled experimental capabilities, output location, successful-shot count,
the submitted action, and per-shot pre- and post-sequence measurements.

### Assessment summary

QuEra through Braket documents comprehensive Analog Hamiltonian Simulation
program and execution provenance. Calibration linkage, compilation history, and
standardized software-access metadata remain partial.

### Evidence references

See the [QuEra evidence ledger](../provider-evidence/quera.md).

---

## Rigetti

### Assessed interfaces

- Rigetti Quantum Cloud Services
- pyQuil 4.17.0
- `quilc`
- QCS SDK
- OpenAPI-specified HTTP API
- gRPC translation and execution APIs

### Findings

Rigetti provides authenticated access to superconducting processors through
Quantum Cloud Services, pyQuil, `quilc`, and the QCS SDK. QCS combines an
OpenAPI-specified HTTP API for accounts, reservations, QPU architecture, and
calibration with a gRPC API for program translation, execution, status, and
result retrieval.

Rigetti documents extensive QPU provenance through instruction-set architecture
and Quil-T calibration resources. These expose:

- physical topology;
- available qubits and couplers;
- native operations by qubit or edge;
- operation and readout performance;
- pulse-level calibration definitions; and
- gate durations derivable from calibrated pulse programs.

The calibration program is the authoritative source for the current native gate
set because operations and available loci may change over time. Some
conventional metrics are less complete: T1 and T2 values are not regularly
published for every current system, and completed jobs are not clearly linked
to immutable historical calibration snapshots.

Circuit and compilation provenance are strongest on the client side. pyQuil
retains the original program, while `quilc` can expose optimized, rewired, and
device-native Quil. The QCS Translation Service applies current Quil-T
calibrations and produces the target-specific executable. The client can inspect
or locally expand the Quil-T representation, but the final executable is
encrypted. Complete pass history, compiler versions, seeds, translation timing,
and calibration association are not automatically retained as job provenance.

Execution results include a job identifier, lifecycle status, readout-register
data, optional raw capture data, and QPU execution duration. The assessed
interfaces do not document a complete set of submission, start, completion, and
queue timestamps. Local software versions, compiler settings, access method,
and retrieval timestamps must be captured by the application.

### Assessment summary

Rigetti documents comprehensive applicable QPU provenance and useful
client-side circuit and compilation information. Persistent circuit
association, lifecycle timing, historical calibration linkage, and standardized
software-access context remain partial.

### Evidence references

See the [Rigetti evidence ledger](../provider-evidence/rigetti.md).

---

## VTT QX

### Assessed interfaces

- VTT QX
- VTT Q5 and VTT Q50
- IQM Client with Qiskit and Cirq adapters
- Authenticated REST API
- IQM Pulla pulse-level access
- Q50 IQM Client versions 34–35
- Q50 IQM Pulla versions 13–14

### Findings

VTT provides authenticated access to VTT Q5 and VTT Q50 through VTT QX,
IQM-compatible clients, and an authenticated REST interface. Pulse-level access
is also available through IQM Pulla.

VTT documents comprehensive QPU provenance. Static and dynamic quantum
architectures identify:

- physical and currently usable qubits;
- couplers;
- connectivity;
- native operations; and
- operation loci.

Each dynamic architecture is tied to a calibration-set identifier.
Calibration interfaces provide current and historical quality metrics,
including:

- T1;
- T2;
- T2 echo;
- readout fidelity;
- directional readout errors;
- single- and two-qubit gate fidelities;
- CZ fidelity;
- metric timestamps;
- uncertainties; and
- calibration- and quality-metric-set identifiers.

A specific calibration set can be selected for execution, and the corresponding
identifier is returned with the job.

Circuit provenance is also strong. Job results preserve the submitted circuit
request, qubit mapping, shot count, and calibration-set identifier. Qiskit and
Cirq expose original and transpiled circuits. Through IQM Pulla, users can
inspect pulse schedules before submission.

Compilation provenance remains partial because transpilation and pulse
generation can be inspected locally, but complete pass history, random seeds,
compiler versions, and compilation timing are not retained as a standardized
job record.

Execution provenance includes job identity and status, retained circuit
requests, raw measurements or aggregated counts, shots, calibration
association, and project and device context. Raw shot-level results can be
converted into counts for large results or following retention policies, and
the API reports the current representation.

Exact client versions, API version, access path, retrieval timestamp, and
field-level availability metadata still require application-side capture.

### Assessment summary

VTT QX documents comprehensive circuit, QPU, characterization, and execution
provenance. Detailed compilation history and standardized software-access
context remain partial.

### Evidence references

See the [VTT QX evidence ledger](../provider-evidence/vtt-qx.md).

---

# Cloud Aggregators

## Amazon Braket

### Assessed interfaces

- Amazon Braket SDK 1.123.0
- Amazon Braket service API
- Gate-model circuits
- OpenQASM 3
- Program sets
- Pulse programs
- Annealing problems
- Analog Hamiltonian Simulation programs

### Findings

Amazon Braket provides authenticated multi-provider access using a common
quantum-task abstraction. At the verification cutoff, Braket documented QPU
access from AQT, IonQ, IQM, QuEra, and Rigetti.

Program and execution provenance are comparatively comprehensive. Task and
result schemas retain:

- the submitted action;
- device and task identifiers;
- shots;
- device parameters;
- result representation;
- lifecycle status;
- creation and completion timestamps;
- successful-shot count;
- queue information;
- failure details;
- tags;
- associations;
- experimental capabilities; and
- provider-specific result metadata.

Technology-specific results include gate-model measurements or probabilities,
annealing solutions and timing data, and neutral-atom pre- and post-sequence
measurements. Braket also identifies whether measurements were returned by the
device or constructed by the SDK from provider-returned probabilities.

Results are stored in customer-controlled Amazon S3 locations and can be
retrieved after the originating client session.

Device properties expose provider and device identity, native operations,
topology, supported result types, execution windows, shot constraints,
standardized qubit properties, provider-specific capabilities, and calibration
data where supplied by the underlying hardware provider. The level of detail
varies across providers. Completed tasks are not consistently associated with
immutable calibration identifiers or historical device-property snapshots.

Compilation provenance remains partial. Users can inspect native gates and
connectivity, manually allocate qubits on supported devices, disable rewiring,
submit native programs, and use verbatim compilation to prevent selected
provider transformations. Ordinary task records do not systematically return:

- the provider-compiled circuit;
- selected qubit mappings;
- pass history;
- compiler version;
- compilation duration; or
- the precise characterization snapshot used during compilation.

Schema and interface versions are available, but local SDK versions, access
method, retrieval timestamp, and field-level availability metadata require
application-side capture.

### Assessment summary

Amazon Braket documents comprehensive cross-provider program and execution
provenance. Characterization linkage, provider compilation history, and
standardized software-access context remain partial and provider-dependent.

### Evidence references

See the [Amazon Braket evidence ledger](../provider-evidence/amazon-braket.md).

---

## Microsoft Azure Quantum

### Assessed interfaces

- Microsoft Quantum Development Kit 1.30.0
- Azure Quantum Python SDK 3.10.0
- Azure Quantum data-plane REST API `2026-01-15-preview`
- Q#
- OpenQASM
- Qiskit
- Cirq
- PennyLane
- QIR
- Provider-native formats

### Findings

Microsoft Azure Quantum provides authenticated access to multiple providers
through the Quantum Development Kit, Python SDK, and data-plane REST API. At
the verification cutoff, Azure Quantum documented hardware access from IonQ,
Pasqal, Quantinuum, and Rigetti. QIR is the principal interoperable submission
representation in the current Quantum Development Kit.

Program provenance is comparatively comprehensive at the submitted-artifact
level. Each job identifies:

- provider;
- target;
- input and output formats;
- input parameters;
- metadata; and
- Azure Blob Storage locations containing the submitted input and returned
  output.

The stored artifact may be QIR or a provider-native representation rather than
the original source-level circuit. Applications should therefore retain both
the source and generated submission artifact.

Azure documents consistent target-discovery information, including target
identity, availability, average queue time, qubit count, QIR profile, status
page, and provider-supplied metadata. It does not normalize detailed topology,
native operations, coherence, fidelity, duration, pulse calibration, or
historical characterization across hardware providers. Immutable
job-to-calibration linkage is not provided through the common Azure job model.

Compilation provenance is partial. Client-side transformations from Q#,
OpenQASM, Qiskit, Cirq, and PennyLane to QIR can be retained, and direct
provider-native formats can provide additional control. Final
provider-compiled programs, qubit mappings, pass histories, compiler versions,
compilation timing, and characterization associations are not systematically
returned with completed jobs.

Execution provenance is stronger. Job records include identifiers, provider
and target context, creator identity, lifecycle status, creation,
execution-start, completion, cancellation, modification, and update timestamps,
errors, priority, sessions, cost estimates, usage metrics, tags, and input and
output storage locations.

Local software versions, compiler versions, retrieval timestamps, and
field-level availability metadata require application-side capture.

### Assessment summary

Azure Quantum documents comprehensive submitted-program and execution
provenance. Normalized hardware characterization, compilation history, and
standardized software-access context remain incomplete.

### Evidence references

See the [Microsoft Azure Quantum evidence ledger](../provider-evidence/azure-quantum.md).

---

## qBraid

### Assessed interfaces

- qBraid Cloud
- qBraid SDK 0.12.2
- qBraid Quantum Runtime API
- qBraid-native runtime
- Direct-provider adapters

### Findings

qBraid provides authenticated multi-provider access through qBraid Cloud, its
SDK, and Quantum Runtime API. The SDK provides both a qBraid-native runtime and
adapters for direct access to external provider services. The aggregator
assessment concerns the native runtime, which assigns common resource
identifiers and normalizes device, job, and result data across gate-based,
analog, and annealing workloads.

Program provenance is comparatively comprehensive. A qBraid job retains:

- its submitted program;
- program format;
- target device;
- shots;
- runtime options;
- metadata;
- tags; and
- grouping information.

The submitted program can be retrieved after execution. qBraid supports
multiple representations, including OpenQASM, QIR, provider-native formats,
Pulser sequences, and analog programs. Automatic conversion may occur before
submission, so the retrieved program can differ from the user's original source
representation. Applications should retain both artifacts.

The common device profile exposes:

- device and provider identifiers;
- hardware modality;
- computational paradigm;
- QPU or simulator type;
- qubit count;
- status;
- queue depth;
- waiting-time and availability estimates where supplied;
- accepted program formats;
- supported noise models;
- pricing;
- active version; and
- batch-job support.

Detailed topology, coherence, fidelity, duration, pulse calibration, historical
characterization, and job-to-calibration information are not consistently
normalized across connected providers.

Compilation provenance remains partial. qBraid provides a conversion graph and
can automatically transpile, transform, validate, and serialize programs into
target-supported representations. The cloud job retains the resulting
submitted program and runtime options but not the full conversion path,
intermediate representations, converter versions, transformation warnings,
compilation timing, or subsequent provider-side compilation decisions.

Execution provenance is stronger. The normalized job model exposes job and
device identifiers, lifecycle status, queue position, timestamps, execution
duration where supplied, shots, grouped and batch execution, errors, costs,
results, tags, metadata, runtime options, and the submitted program.

Exact local framework versions, API version, retrieval timestamp, and
field-level availability metadata require application-side capture.

### Assessment summary

qBraid documents comprehensive submitted-program and execution provenance.
Normalized QPU characterization, compilation history, and standardized
software-access context remain partial.

### Evidence references

See the [qBraid evidence ledger](../provider-evidence/qbraid.md).

---

# Cross-Platform Interpretation

The detailed profiles support three principal findings.

First, job identity, lifecycle status, timestamps, shots, and final results are
the most consistently documented provenance across provider and aggregator
interfaces.

Second, device characterization varies both by hardware technology and by the
strength of its association with a particular execution. Some platforms
document immutable or selectable characterization identifiers, while others
provide only current or nearest-available device properties.

Third, compilation provenance remains predominantly client-side. Most
interfaces permit inspection of a transpiled, routed, decomposed, discretized,
or otherwise target-compatible program before submission, but comparatively
few retain a complete provider-side transformation history with compiler
versions, pass sequences, random seeds, timings, and intermediate artifacts.

Software versions, access methods, retrieval timestamps, and explicit
field-level availability metadata are also generally left to the consuming
application.

These findings motivate an evidence-aware provenance model that normalizes
record structure while preserving:

- provider-supplied values;
- information passed through an aggregator;
- derived values;
- application-captured context;
- unavailable information;
- inapplicable attributes; and
- the temporal association between execution and device characterization.

---

# Excluded or Retired Platforms

## Xanadu Cloud

Xanadu Cloud was not included in the final comparative platform sample because
the formerly public hardware cloud service was no longer available at the July
19, 2026 verification cutoff.

Strawberry Fields and PennyLane continue to document photonic device
specifications and simulator capabilities, including numbers of modes, allowed
operations, phase ranges, topology, loss, detector models, squeezing
parameters, and other photonic concepts. These software capabilities remain
relevant to provenance modeling but were not treated as evidence of a
currently verifiable public hardware-service interface.

---

# Artifact Maintenance Notes

When updating this supplementary document:

1. record the new verification date;
2. retain the previous archived version for reproducibility;
3. update assessed SDK and API versions;
4. distinguish interface changes from changes in evidence interpretation;
5. regenerate the comparative coverage matrix if a rating changes;
6. avoid converting absence of public evidence into a claim that the provider
   does not support a capability; and
7. identify any findings established through provider-authorized validation
   separately from findings based only on public evidence.
