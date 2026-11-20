"""Live Amazon Braket retrieval through the integration ``ProviderAdapter`` seam.

Maps the Braket control-plane responses (``GetQuantumTask``, ``GetDevice``) and
the ``results.json`` object the service writes to the customer's S3 bucket into
the integration data transfer objects consumed by the provenance adapters.

Choices that affect provenance semantics, kept deliberately close to what a
Braket SDK-based integration hands to an application:

* ``measurement_counts`` are tallied from ``measurements`` when the result has
  per-shot measurements. When the device returns only
  ``measurementProbabilities`` (IonQ through Braket), counts are expanded as
  ``round(p * shots)``, which is what ``GateModelQuantumTaskResult`` does. The
  untouched result object is kept in ``raw_payload`` so this remains visible.
* ``calibration_data.captured_at`` is taken only from
  ``standardized.updatedAt``. The service-document ``service.updatedAt`` is not
  a characterization timestamp and is recorded separately.
* Per-qubit standardized properties are summarized as medians over qubits or
  pairs (``...median_over_qubits`` / ``...median_over_pairs``, provider unit in
  brackets); the full standardized block is kept under
  ``calibration_data.standardized``.
"""

from __future__ import annotations

import json
from collections import Counter
from statistics import median
from typing import Any

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
    ThrottledError,
)
from .sanitize import ACCOUNT_PLACEHOLDER

_NOT_FOUND = {"ResourceNotFoundException", "NoSuchKey", "NoSuchBucket", "404"}
_DENIED = {
    "AccessDeniedException",
    "AccessDenied",
    "UnrecognizedClientException",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "ExpiredToken",
    "ExpiredTokenException",
    "ExpiredTokenException",
    "InvalidSignatureException",
    "403",
}
_THROTTLED = {"ThrottlingException", "TooManyRequestsException", "SlowDown"}


def _region_from_arn(arn: str) -> str | None:
    parts = arn.split(":")
    return parts[3] or None if len(parts) > 3 else None


def _translate(exc: Exception, what: str) -> ProviderIntegrationError:
    response = getattr(exc, "response", None)  # None on botocore timeouts
    code = (response or {}).get("Error", {}).get("Code", "") if isinstance(response, dict) else ""
    message = f"{what}: {code or type(exc).__name__}: {exc}"
    if code in _NOT_FOUND:
        return JobNotFoundError(message)
    if code in _DENIED:
        return AccessDeniedError(message)
    if code in _THROTTLED:
        return ThrottledError(message)
    return ProviderIntegrationError(message)


def _parse_json(body: Any, what: str) -> Any:
    try:
        return json.loads(body)
    except ValueError as exc:  # malformed or truncated document
        raise ProviderIntegrationError(f"{what}: unreadable JSON: {exc}") from exc


_AHS_STATES = "erg"


def ahs_site_counts(measurements: list[dict[str, Any]]) -> dict[str, int]:
    """Analog (AHS) shots as site-state strings, as the Braket SDK's ``get_counts``.

    Per site: ``e`` empty (pre-sequence 0), ``r`` Rydberg (post-sequence 0),
    ``g`` ground (post-sequence 1). Only shots with status ``Success`` count.
    """

    tally: Counter[str] = Counter()
    for shot in measurements:
        if (shot.get("shotMetadata") or {}).get("shotStatus") != "Success":
            continue
        result = shot.get("shotResult") or {}
        pre, post = result.get("preSequence") or [], result.get("postSequence") or []
        tally[
            "".join(
                _AHS_STATES[0 if a == 0 else 1 if b == 0 else 2]
                for a, b in zip(pre, post, strict=True)
            )
        ] += 1
    return dict(tally)


def counts_from_result(result: dict[str, Any], shots: int | None) -> tuple[dict[str, int], str]:
    """Return measurement counts and how they were obtained."""

    measurements = result.get("measurements")
    if measurements:
        if all(isinstance(shot, dict) and "shotResult" in shot for shot in measurements):
            return ahs_site_counts(measurements), "observed_ahs_site_states"
        if not all(
            isinstance(shot, list) and all(bit in (0, 1) for bit in shot) for shot in measurements
        ):
            # Tallying an unknown shot layout would invent outcomes (F15).
            return {}, "unrecognized_shot_format"
        tally = Counter("".join(str(bit) for bit in shot) for shot in measurements)
        return dict(tally), "observed_measurements"
    probabilities = result.get("measurementProbabilities")
    if probabilities and shots:
        expanded = {k: int(round(p * shots)) for k, p in probabilities.items()}
        return {k: v for k, v in expanded.items() if v}, "expanded_from_measurementProbabilities"
    return {}, "none"


def summarize_calibration(capabilities: dict[str, Any]) -> dict[str, Any] | None:
    standardized = capabilities.get("standardized") or {}
    provider = capabilities.get("provider") or {}
    metrics: dict[str, float] = {}

    for group in ("fidelity", "timing"):
        for key, value in (provider.get(group) or {}).items():
            if isinstance(value, dict) and isinstance(value.get("mean"), (int, float)):
                metrics[f"provider.{group}.{key}.mean"] = float(value["mean"])
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[f"provider.{group}.{key}"] = float(value)

    one_qubit = standardized.get("oneQubitProperties") or {}
    if one_qubit:
        series: dict[str, list[float]] = {}
        for props in one_qubit.values():
            for name in ("T1", "T2"):
                entry = props.get(name) or {}
                if isinstance(entry.get("value"), (int, float)):
                    unit = f"[{entry['unit']}]" if entry.get("unit") else ""
                    series.setdefault(f"standardized.{name}{unit}", []).append(
                        float(entry["value"])
                    )
            for entry in props.get("oneQubitFidelity") or []:
                kind = (entry.get("fidelityType") or {}).get("name", "UNKNOWN")
                if isinstance(entry.get("fidelity"), (int, float)):
                    series.setdefault(f"standardized.oneQubitFidelity.{kind}", []).append(
                        float(entry["fidelity"])
                    )
        metrics.update({f"{k}.median_over_qubits": median(v) for k, v in series.items()})

    two_qubit = standardized.get("twoQubitProperties") or {}
    if two_qubit:
        series = {}
        for props in two_qubit.values():
            for entry in props.get("twoQubitGateFidelity") or []:
                kind = (entry.get("fidelityType") or {}).get("name", "UNKNOWN")
                gate = entry.get("gateName", "UNKNOWN")
                if isinstance(entry.get("fidelity"), (int, float)):
                    series.setdefault(
                        f"standardized.twoQubitGateFidelity.{gate}.{kind}", []
                    ).append(float(entry["fidelity"]))
        metrics.update({f"{k}.median_over_pairs": median(v) for k, v in series.items()})

    for key, value in standardized.items():
        if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
            metrics[f"standardized.{key}"] = float(value["value"])

    if not metrics:
        return None
    return {
        "captured_at": standardized.get("updatedAt"),
        "service_updated_at": (capabilities.get("service") or {}).get("updatedAt"),
        "metrics": metrics,
        "standardized": standardized or None,
    }


class LiveBraketIntegration(ProviderAdapter):
    """Retrieval against the Amazon Braket service and the task's S3 output."""

    provider = "braket"

    def __init__(self, session: Any | None = None) -> None:
        if session is None:
            import boto3

            session = boto3.Session()
        self._session = session
        self.native: dict[str, Any] = {}
        self.notes: dict[str, Any] = {}

    def _braket(self, region: str | None):
        return self._session.client("braket", region_name=region)

    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        if f":{ACCOUNT_PLACEHOLDER}:" in provider_job_id:
            account = self._session.client("sts").get_caller_identity()["Account"]
            provider_job_id = provider_job_id.replace(f":{ACCOUNT_PLACEHOLDER}:", f":{account}:")
        return TaskHandle(
            provider="braket",
            provider_job_id=provider_job_id,
            region=region or _region_from_arn(provider_job_id),
        )

    def _task(self, task: TaskHandle) -> dict[str, Any]:
        if task.raw_task is None:
            try:
                response = self._braket(task.region).get_quantum_task(
                    quantumTaskArn=task.provider_job_id, additionalAttributeNames=["QueueInfo"]
                )
            except Exception as exc:
                raise _translate(exc, "GetQuantumTask") from exc
            response.pop("ResponseMetadata", None)
            self.native["get_quantum_task"] = response
            task.raw_task = response
            task.target_id = task.provider_target_id = response.get("deviceArn")
        return task.raw_task

    def get_status(self, task: TaskHandle) -> TaskSnapshot:
        raw = self._task(task)
        return TaskSnapshot(
            provider="braket",
            provider_job_id=task.provider_job_id,
            status=str(raw.get("status", "UNKNOWN")),
            created_at=raw.get("createdAt"),
            ended_at=raw.get("endedAt"),
            shots=raw.get("shots"),
            target_id=raw.get("deviceArn"),
            provider_target_id=raw.get("deviceArn"),
            metadata=dict(raw),
        )

    def _results_json(self, task: TaskHandle) -> dict[str, Any]:
        if "results_json" not in self.native:
            raw = self._task(task)
            bucket, directory = raw.get("outputS3Bucket"), raw.get("outputS3Directory")
            if not bucket or not directory:
                raise ResultUnavailableError("Task has no S3 output location")
            try:
                obj = self._session.client("s3", region_name=task.region).get_object(
                    Bucket=bucket, Key=f"{directory}/results.json"
                )
                body = obj["Body"].read()
            except Exception as exc:
                raise _translate(exc, "S3 GetObject results.json") from exc
            self.native["results_json"] = _parse_json(body, "S3 results.json")
        return self.native["results_json"]

    def get_result(self, task: TaskHandle) -> TaskResult:
        raw = self._task(task)
        status = str(raw.get("status", "UNKNOWN"))
        if status != "COMPLETED":
            raise ResultUnavailableError(f"Task is not complete: {status}")
        result = self._results_json(task)
        counts, origin = counts_from_result(result, raw.get("shots"))
        self.notes["measurement_counts_origin"] = origin
        source = ((result.get("additionalMetadata") or {}).get("action") or {}).get("source")
        self.notes["submitted_program_available"] = bool(source)
        compiled = self.get_compiled_circuit(task)
        self.notes["compiled_program"] = (
            "absent" if compiled is None else "present_empty" if not compiled else "present"
        )
        return TaskResult(
            provider="braket",
            provider_job_id=task.provider_job_id,
            status=status,
            measurement_counts=counts,
            compiled_circuit=compiled,
            compiled_circuit_metrics=None,
            raw_payload=result,
        )

    def get_compiled_circuit(self, task: TaskHandle) -> str | None:
        try:
            result = self._results_json(task)
        except ProviderIntegrationError:
            return None
        for key, block in (result.get("additionalMetadata") or {}).items():
            if key.endswith("Metadata") and isinstance(block, dict) and "compiledProgram" in block:
                program = block["compiledProgram"]
                return program if isinstance(program, str) else json.dumps(program, sort_keys=True)
        return None

    def get_device_details(self, target_id: str, region: str | None = None) -> DeviceDetails:
        try:
            response = self._braket(region or _region_from_arn(target_id)).get_device(
                deviceArn=target_id
            )
        except Exception as exc:
            raise _translate(exc, "GetDevice") from exc
        response.pop("ResponseMetadata", None)
        capabilities = _parse_json(response.get("deviceCapabilities") or "{}", "deviceCapabilities")
        self.native["get_device"] = {**response, "deviceCapabilities": capabilities}
        paradigm = capabilities.get("paradigm") or {}
        return DeviceDetails(
            provider="braket",
            target_id=target_id,
            provider_target_id=target_id,
            name=response.get("deviceName"),
            type=response.get("deviceType"),
            status=response.get("deviceStatus"),
            calibration_data=summarize_calibration(capabilities),
            provider_properties={
                k: paradigm[k] for k in ("qubitCount", "nativeGateSet") if k in paradigm
            }
            or None,
            metadata={"provider": response.get("providerName")},
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


__all__ = [
    "LiveBraketIntegration",
    "ahs_site_counts",
    "counts_from_result",
    "summarize_calibration",
]
