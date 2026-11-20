"""Live IBM Quantum retrieval through the integration ``ProviderAdapter`` seam.

Uses ``qiskit-ibm-runtime`` (``RuntimeJobV2``, ``IBMBackend``), the client a
Qiskit-based application uses, and maps job, metrics, result and backend data
into the integration data transfer objects.

Choices that affect provenance semantics:

* ``measurement_counts`` are tallied from the Sampler V2 per-shot bit arrays of
  the first PUB, so they are observed counts. Estimator results carry no counts.
* Backend properties are requested **as of job creation**
  (``properties(datetime=created)``); IBM returns the latest snapshot at or
  before that time. ``calibration_data.captured_at`` is that snapshot's
  ``last_update_date``.
* ``compiled_circuit`` is the first PUB circuit of the job inputs serialized
  as OpenQASM 3. With Sampler/Estimator V2 the application submits ISA
  circuits it compiled itself, so this program is application-compiled and
  merely returned by the provider; ``notes["compiled_program_origin"]`` says so.
"""

from __future__ import annotations

import os
from statistics import median
from typing import Any

from .sanitize import to_jsonable
from ..integration import (
    AccessDeniedError,
    DeviceDetails,
    JobNotFoundError,
    ProviderAdapter,
    ProviderIntegrationError,
    ResolvedTarget,
    ResultUnavailableError,
    SubmissionResult,
    TargetInfo,
    TaskHandle,
    TaskResult,
    TaskSnapshot,
)

_DONE = {"DONE", "COMPLETED"}


def _translate(exc: Exception, what: str) -> ProviderIntegrationError:
    text = f"{what}: {type(exc).__name__}: {exc}"
    lowered = str(exc).lower()
    if "not found" in lowered or "404" in lowered:
        return JobNotFoundError(text)
    if "unauthorized" in lowered or "forbidden" in lowered or "401" in lowered or "403" in lowered:
        return AccessDeniedError(text)
    return ProviderIntegrationError(text)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def summarize_properties(props: dict[str, Any]) -> dict[str, Any] | None:
    """Summarize IBM ``BackendProperties.to_dict()`` as medians with provider units.

    Medians, because IBM reports unusable qubits and gates with extreme error
    values that dominate a mean; units stay in the metric name because IBM
    reports times in microseconds while other providers use seconds.
    """

    series: dict[str, list[float]] = {}
    for qubit in props.get("qubits") or []:
        for entry in qubit:
            if entry.get("name") in {"T1", "T2", "readout_error"} and isinstance(
                entry.get("value"), (int, float)
            ):
                unit = f"[{entry['unit']}]" if entry.get("unit") else ""
                series.setdefault(f"{entry['name']}.median_over_qubits{unit}", []).append(
                    float(entry["value"])
                )
    for gate in props.get("gates") or []:
        for entry in gate.get("parameters") or []:
            if entry.get("name") == "gate_error" and isinstance(entry.get("value"), (int, float)):
                series.setdefault(f"gate_error.{gate.get('gate')}.median", []).append(
                    float(entry["value"])
                )
    if not series:
        return None
    return {
        "captured_at": _iso(props.get("last_update_date")),
        "metrics": {name: median(values) for name, values in series.items()},
    }


def _shots(inputs: dict[str, Any]) -> int | None:
    """Shots as recorded in the job inputs (schema v2 QuantumProgram or PUBs)."""

    program = inputs.get("quantum_program")
    if program is not None and isinstance(getattr(program, "shots", None), int):
        return program.shots
    for pub in inputs.get("pubs") or []:
        if isinstance(pub, (list, tuple)) and len(pub) >= 3 and isinstance(pub[2], int):
            return pub[2]
        if isinstance(getattr(pub, "shots", None), int):
            return pub.shots
    for key in ("shots", "default_shots"):
        if isinstance(inputs.get(key), int):
            return inputs[key]
    return None


def _post_processor(inputs: dict[str, Any]) -> dict[str, Any]:
    """Primitive options the client passed through the executor job (schema v2.0)."""

    program = inputs.get("quantum_program")
    passthrough = getattr(program, "passthrough_data", None) or {}
    value = passthrough.get("post_processor") if isinstance(passthrough, dict) else None
    return value if isinstance(value, dict) else {}


def _requested_shots(inputs: dict[str, Any]) -> int | None:
    """Shots the primitive caller asked for; falls back to the executor shots."""

    shots = _post_processor(inputs).get("shots")
    return shots if isinstance(shots, int) else _shots(inputs)


def _executed_shots(inputs: dict[str, Any]) -> int | None:
    """Executor shots summed over items and their randomizations (schema v2.0)."""

    program = inputs.get("quantum_program")
    if program is None or not isinstance(getattr(program, "shots", None), int):
        return None
    total = 0
    for item in program.items:
        shape = getattr(item, "shape", None)
        if shape is None:
            return None
        size = 1
        for dim in shape:
            size *= int(dim)
        total += size * program.shots
    return total


def _runtime_version() -> str:
    try:
        from qiskit_ibm_runtime import __version__
    except ImportError:  # pragma: no cover - live extra not installed
        return "unknown"
    return str(__version__)


def _first_circuit(inputs: dict[str, Any]):
    program = inputs.get("quantum_program")
    for item in getattr(program, "items", None) or []:
        if hasattr(getattr(item, "circuit", None), "num_qubits"):
            return item.circuit
    for pub in inputs.get("pubs") or []:
        circuit = pub[0] if isinstance(pub, (list, tuple)) else getattr(pub, "circuit", pub)
        if hasattr(circuit, "num_qubits"):
            return circuit
    return None


class LiveIBMIntegration(ProviderAdapter):
    """Retrieval against IBM Quantum through ``QiskitRuntimeService``."""

    provider = "ibm"

    def __init__(self, service: Any | None = None) -> None:
        if service is None:
            from qiskit_ibm_runtime import QiskitRuntimeService

            service = QiskitRuntimeService(
                channel="ibm_quantum_platform",
                token=os.environ["IBM_QUANTUM_API_KEY"],
                instance=os.environ["IBM_QUANTUM_INSTANCE_CRN"],
            )
        self._service = service
        self._jobs: dict[str, Any] = {}
        self._created_at: Any | None = None
        self.native: dict[str, Any] = {}
        self.notes: dict[str, Any] = {}

    def _job(self, job_id: str):
        if job_id not in self._jobs:
            try:
                self._jobs[job_id] = self._service.job(job_id)
            except Exception as exc:
                raise _translate(exc, "service.job") from exc
        return self._jobs[job_id]

    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        return TaskHandle(provider="ibm", provider_job_id=provider_job_id, region=region)

    def get_status(self, task: TaskHandle) -> TaskSnapshot:
        job = self._job(task.provider_job_id)
        try:
            status = str(job.status())
            metrics = job.metrics() or {}
            inputs = job.inputs or {}
        except Exception as exc:
            raise _translate(exc, "RuntimeJobV2 status/metrics") from exc
        backend = job.backend()
        backend_name = getattr(backend, "name", None) or str(backend)
        timestamps = metrics.get("timestamps") or {}
        self._created_at = job.creation_date
        program = inputs.get("quantum_program")
        input_schema = inputs.get("schema_version") or ("pubs" if "pubs" in inputs else None)
        if input_schema is None:
            input_schema = "unrecognized:" + ",".join(sorted(map(str, inputs)))
        self.notes["input_schema"] = input_schema
        self.notes["primitive_recorded"] = getattr(job, "primitive_id", None)
        if program is not None:
            self.notes["input_items"] = [type(item).__name__ for item in program.items]
        self.native["job"] = {
            "job_id": job.job_id(),
            "status": status,
            "creation_date": _iso(job.creation_date),
            "backend": backend_name,
            "primitive_id": getattr(job, "primitive_id", None),
            "session_id": getattr(job, "session_id", None),
            "usage_estimation": getattr(job, "usage_estimation", None),
        }
        self.native["metrics"] = metrics
        session_id = getattr(job, "session_id", None)
        session_mode = None
        if session_id:
            # Batch vs session mode is only on the session resource; the SDK has
            # no public accessor for it.
            try:
                details = self._service._get_api_client().session_details(session_id) or {}
            except Exception as exc:
                self.notes["session_details_error"] = f"{type(exc).__name__}: {exc}"[:200]
            else:
                self.native["session"] = details
                session_mode = details.get("mode")
        error_message = None
        if status in ("ERROR", "FAILED"):
            try:
                error_message = job.error_message()
            except Exception as exc:
                self.notes["error_message_error"] = f"{type(exc).__name__}: {exc}"[:200]
        task.target_id = task.provider_target_id = backend_name
        return TaskSnapshot(
            provider="ibm",
            provider_job_id=task.provider_job_id,
            status=status,
            created_at=job.creation_date,
            ended_at=timestamps.get("finished"),
            shots=_requested_shots(inputs),
            target_id=backend_name,
            provider_target_id=backend_name,
            metadata={
                "backend_name": backend_name,
                "program_id": getattr(job, "primitive_id", None),
                "session_id": session_id,
                "session_mode": session_mode,
                "input_schema": input_schema,
                "error_message": error_message,
                "timestamps": timestamps,
                "usage": metrics.get("usage"),
                "qiskit_version": metrics.get("qiskit_version"),
                "shots": _requested_shots(inputs),
                "executor_shots": _shots(inputs),
                "executed_shots": (_executed_shots(inputs) if status.upper() in _DONE else None),
                "resilience_level": (_post_processor(inputs).get("options") or {}).get(
                    "resilience_level"
                ),
            },
        )

    def get_result(self, task: TaskHandle) -> TaskResult:
        job = self._job(task.provider_job_id)
        status = str(job.status())
        if status.upper() not in _DONE:
            raise ResultUnavailableError(f"Job is not complete: {status}")
        try:
            result = job.result()
        except Exception as exc:
            raise _translate(exc, "RuntimeJobV2.result") from exc
        counts: dict[str, int] = {}
        raw_payload = None
        kind = "none"
        if len(result):
            data = result[0].data
            for name in data:
                bits = getattr(data[name], "get_counts", None)
                if bits is not None:
                    counts = {k: int(v) for k, v in bits().items()}
                    kind = f"observed_samples:{name}"
                    break
            else:
                kind = "no_bit_arrays"
            if not counts and "evs" in data:
                # Executor-based EstimatorV2: IBM returns per-shot samples; the SDK's
                # client-side decoder computes the expectation values from them.
                raw_payload = {
                    "primitive": "estimator",
                    "evs": to_jsonable(data["evs"]),
                    "stds": to_jsonable(data["stds"]) if "stds" in data else None,
                    "ensemble_standard_error": (
                        to_jsonable(data["ensemble_standard_error"])
                        if "ensemble_standard_error" in data
                        else None
                    ),
                    "decoder_chain": " -> ".join(
                        d.__name__ for d in getattr(job, "_result_decoders", None) or []
                    ),
                    "client": f"qiskit-ibm-runtime {_runtime_version()}",
                }
                kind = "expectation_values:client_side_decoder"
        self.notes["measurement_counts_origin"] = kind
        self.native["result_metadata"] = getattr(result, "metadata", None)
        return TaskResult(
            provider="ibm",
            provider_job_id=task.provider_job_id,
            status=status,
            measurement_counts=counts,
            compiled_circuit=self.get_compiled_circuit(task),
            compiled_circuit_metrics=None,
            raw_payload=raw_payload,
        )

    def get_compiled_circuit(self, task: TaskHandle) -> str | None:
        circuit = _first_circuit(self._job(task.provider_job_id).inputs or {})
        if circuit is None:
            self.notes["compiled_program_origin"] = "absent"
            return None
        from qiskit import qasm3

        self.notes["compiled_program_origin"] = "application_compiled_job_input"
        self.notes["submitted_program_available"] = True
        return qasm3.dumps(circuit)

    def get_device_details(self, target_id: str, region: str | None = None) -> DeviceDetails:
        try:
            backend = self._service.backend(target_id)
            config = backend.configuration()
            created = self._created_at
            properties = backend.properties(datetime=created) if created else backend.properties()
            status = backend.status()
        except Exception as exc:
            raise _translate(exc, "IBMBackend configuration/properties") from exc
        props = properties.to_dict() if properties is not None else {}
        self.notes["properties_query"] = "as_of_job_creation" if created else "current"
        calibration = summarize_properties(props)
        if calibration is not None:
            calibration["query"] = self.notes["properties_query"]
        self.native["backend_configuration"] = {
            "backend_name": config.backend_name,
            "backend_version": getattr(config, "backend_version", None),
            "n_qubits": config.n_qubits,
            "processor_type": getattr(config, "processor_type", None),
            "basis_gates": config.basis_gates,
        }
        self.native["backend_properties_last_update_date"] = _iso(props.get("last_update_date"))
        return DeviceDetails(
            provider="ibm",
            target_id=target_id,
            provider_target_id=target_id,
            name=config.backend_name,
            type="QPU" if not getattr(config, "simulator", False) else "SIMULATOR",
            status="ONLINE" if status.operational else "OFFLINE",
            calibration_data=calibration,
            provider_properties={
                "num_qubits": config.n_qubits,
                "processor_type": getattr(config, "processor_type", None),
                "basis_gates": list(config.basis_gates),
            },
            metadata={"provider": "IBM Quantum"},
        )

    # -- submission is out of scope for provenance retrieval -----------------

    def list_targets(self, region: str | None = None) -> list[TargetInfo]:
        raise NotImplementedError

    def resolve_target(self, target_id: str, region: str | None = None) -> ResolvedTarget:
        raise NotImplementedError

    def submit_openqasm(
        self,
        openqasm: str,
        shots: int,
        target: ResolvedTarget,
        s3_bucket: str | None = None,
        s3_prefix: str | None = None,
    ) -> SubmissionResult:
        raise NotImplementedError


__all__ = ["LiveIBMIntegration", "summarize_properties"]
