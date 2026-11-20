"""Stage A: transport faults at each live retrieval layer.

A fake client per library answers normally except at one operation, where it
raises what that library raises for the fault (or returns the faulty body).
The outcome is the exception that leaves the retrieval layer.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from typing import Any

from .. import integration

FAULTS = ("timeout", "401", "403", "404", "429", "500", "503", "malformed", "truncated")
OPERATIONS = ("get_status", "get_result", "get_device_details")
EXPECTED = {
    "timeout": "ProviderIntegrationError",
    "401": "AccessDeniedError",
    "403": "AccessDeniedError",
    "404": "JobNotFoundError",
    "429": "ThrottledError",
    "500": "ProviderIntegrationError",
    "503": "ProviderIntegrationError",
    "malformed": "ProviderIntegrationError",
    "truncated": "ProviderIntegrationError",
}
_REASONS = {
    "401": "Unauthorized",
    "403": "Forbidden",
    "404": "Not Found",
    "429": "Too Many Requests",
    "500": "Internal Server Error",
    "503": "Service Unavailable",
}


def _bad_body(fault: str, normal: Any) -> bytes:
    text = json.dumps(normal)
    return b"{not json" if fault == "malformed" else text[: len(text) // 2].encode()


# -- IonQ (httpx) --------------------------------------------------------------


def _ionq(operation: str, fault: str):
    import httpx

    from ..live.ionq import API, LiveIonQIntegration

    job = {
        "id": "j1",
        "status": "completed",
        "backend": "qpu.forte-1",
        "shots": 100,
        "submitted_at": "2026-11-19T08:28:22Z",
        "completed_at": "2026-11-19T08:30:00Z",
        "execution_duration_ms": 10,
        "stats": {"qubits": 2},
        "output": {},
        "results": {"probabilities": {"url": "/v0.4/jobs/j1/results/probabilities"}},
    }
    routes = {
        "/v0.4/jobs/j1": ("get_status", job),
        "/v0.4/jobs/j1/results/probabilities": ("get_result", {"0": 0.5, "3": 0.5}),
        "/v0.4/backends/qpu.forte-1": ("get_device_details", {"backend": "qpu.forte-1"}),
        "/v0.4/backends/qpu.forte-1/characterizations": ("other", {"characterizations": []}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        op, body = routes[request.url.path]
        if op != operation:
            return httpx.Response(200, json=body)
        if fault == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if fault in ("malformed", "truncated"):
            return httpx.Response(200, content=_bad_body(fault, body))
        return httpx.Response(int(fault), json={"error": _REASONS[fault]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=API)
    return LiveIonQIntegration(client=client), "j1"


# -- Amazon Braket (boto3) -----------------------------------------------------

_BRAKET_CODES = {
    "braket": {
        "401": "UnrecognizedClientException",
        "403": "AccessDeniedException",
        "404": "ResourceNotFoundException",
        "429": "ThrottlingException",
        "500": "InternalServiceException",
        "503": "ServiceUnavailableException",
    },
    "s3": {
        "401": "InvalidAccessKeyId",
        "403": "AccessDenied",
        "404": "NoSuchKey",
        "429": "SlowDown",
        "500": "InternalError",
        "503": "ServiceUnavailable",
    },
}


def _braket(operation: str, fault: str):
    from botocore.exceptions import ClientError, ReadTimeoutError

    from ..live.braket import LiveBraketIntegration

    arn = "arn:aws:braket:us-east-1:123456789012:quantum-task/t1"
    device = "arn:aws:braket:us-east-1::device/qpu/rigetti/Ankaa-3"
    task = {
        "quantumTaskArn": arn,
        "status": "COMPLETED",
        "deviceArn": device,
        "shots": 10,
        "outputS3Bucket": "b",
        "outputS3Directory": "d",
    }
    capabilities = {"paradigm": {"qubitCount": 84}, "service": {}}
    result = {"measurements": [[0, 1]] * 10, "additionalMetadata": {}}

    def fail(service: str, name: str):
        if fault == "timeout":
            raise ReadTimeoutError(endpoint_url=f"https://{service}.us-east-1.amazonaws.com")
        code = _BRAKET_CODES[service][fault]
        raise ClientError(
            {
                "Error": {"Code": code, "Message": _REASONS[fault]},
                "ResponseMetadata": {"HTTPStatusCode": int(fault)},
            },
            name,
        )

    class Braket:
        def get_quantum_task(self, **_):
            if operation == "get_status" and fault not in ("malformed", "truncated"):
                fail("braket", "GetQuantumTask")
            return dict(task)

        def get_device(self, **_):
            if operation == "get_device_details":
                if fault in ("malformed", "truncated"):
                    return {
                        "deviceName": "Ankaa-3",
                        "deviceType": "QPU",
                        "deviceCapabilities": _bad_body(fault, capabilities).decode(),
                    }
                fail("braket", "GetDevice")
            return {
                "deviceName": "Ankaa-3",
                "deviceType": "QPU",
                "deviceStatus": "ONLINE",
                "providerName": "Rigetti",
                "deviceCapabilities": json.dumps(capabilities),
            }

    class S3:
        def get_object(self, **_):
            if operation == "get_result":
                if fault in ("malformed", "truncated"):
                    return {"Body": io.BytesIO(_bad_body(fault, result))}
                fail("s3", "GetObject")
            return {"Body": io.BytesIO(json.dumps(result).encode())}

    class Session:
        def client(self, name, region_name=None):
            return Braket() if name == "braket" else S3()

    if operation == "get_status" and fault in ("malformed", "truncated"):
        return None, None  # boto3 parses the API response itself: not applicable
    return LiveBraketIntegration(session=Session()), arn


# -- IBM (qiskit-ibm-runtime) --------------------------------------------------


def _ibm(operation: str, fault: str):
    from qiskit_ibm_runtime.api.exceptions import RequestsApiError
    from qiskit_ibm_runtime.exceptions import IBMRuntimeError, RuntimeJobNotFound

    from ..live.ibm import LiveIBMIntegration

    def api_error() -> Exception:
        if fault == "timeout":
            return RequestsApiError(
                "HTTPSConnectionPool(host='quantum.cloud.ibm.com', port=443): "
                "Read timed out. (read timeout=60)",
                status_code=-1,
            )
        if fault in ("malformed", "truncated"):
            return json.JSONDecodeError("Expecting value", "{not json", 1)
        return RequestsApiError(
            f"'{fault} Client Error: {_REASONS[fault]} for url: "
            "https://quantum.cloud.ibm.com/api/v1/jobs/d1abc'",
            status_code=int(fault),
        )

    class Job:
        creation_date = None
        primitive_id = "sampler"
        session_id = None
        inputs: dict = {}

        def job_id(self):
            return "d1abc"

        def status(self):
            return "DONE"

        def metrics(self):
            return {"timestamps": {}}

        def backend(self):
            return type("B", (), {"name": "ibm_aachen"})()

        def result(self):
            if operation == "get_result":
                raise api_error()
            return []

    class Backend:
        def configuration(self):
            return type(
                "C",
                (),
                {
                    "backend_name": "ibm_aachen",
                    "n_qubits": 156,
                    "basis_gates": ["cz"],
                    "simulator": False,
                },
            )()

        def properties(self, datetime=None):
            if operation == "get_device_details":
                raise api_error()
            return None

        def status(self):
            return type("S", (), {"operational": True})()

    class Service:
        def job(self, job_id):
            if operation == "get_status":
                error = api_error()
                # As QiskitRuntimeService.job wraps the client error.
                if isinstance(error, RequestsApiError):
                    if error.status_code == 404:
                        raise RuntimeJobNotFound(f"Job not found: {job_id}")
                    raise IBMRuntimeError(f"Failed to retrieve job: {error}")
                raise error
            return Job()

        def backend(self, name):
            return Backend()

    return LiveIBMIntegration(service=Service()), "d1abc"


# -- Quandela (Perceval RPCHandler over requests) ------------------------------


def _quandela(operation: str, fault: str):
    import requests

    from ..live.quandela import LiveQuandelaIntegration

    def http_error(where: str) -> Exception:
        if fault == "timeout":
            return requests.ReadTimeout(f"Read timed out ({where})")
        if fault in ("malformed", "truncated") and where != "results":
            # RPCHandler.get_request converts an unreadable body to HTTPError.
            return requests.HTTPError(f"Could not read json response from url: {where}")
        response = requests.Response()
        response.status_code = int(fault)
        return requests.HTTPError(f"{fault} Client Error: {_REASONS[fault]}", response=response)

    class Handler:
        def get_job_status(self, job_id):
            if operation == "get_status":
                raise http_error("status")
            return {
                "status": "completed",
                "creation_datetime": 1795078368.6,
                "start_time": 1795078380.4,
                "duration": 17,
                "shots": 100,
            }

        def get_job_results(self, job_id):
            if operation == "get_result":
                if fault in ("malformed", "truncated"):
                    # The layer parses the inner results document itself.
                    return {
                        "job_id": job_id,
                        "results": _bad_body(fault, {"results": "x"}).decode(),
                    }
                raise http_error("results")
            return {"job_id": job_id, "results": json.dumps({})}

        def fetch_platform_details(self):
            if operation == "get_device_details":
                raise http_error("platform")
            return {"type": "simulator", "status": "available", "perfs": {}, "specs": {}}

    return LiveQuandelaIntegration(handler_factory=lambda platform: Handler()), "sim:belenos/j1"


BUILDERS: dict[str, Callable[[str, str], tuple[Any, Any]]] = {
    "braket": _braket,
    "ibm": _ibm,
    "ionq": _ionq,
    "quandela": _quandela,
}


def run_cell(provider: str, operation: str, fault: str) -> dict[str, Any]:
    live, job_ref = BUILDERS[provider](operation, fault)
    if live is None:
        return {"outcome": "not_applicable"}
    raised: Exception | None = None
    try:
        handle = live.get_task(job_ref)
        snapshot = live.get_status(handle)
        if operation in ("get_result", "get_device_details") or True:
            if operation == "get_device_details":
                live.get_device_details(snapshot.target_id or handle.target_id or "x")
            elif operation == "get_result":
                live.get_result(handle)
    except Exception as exc:  # noqa: BLE001 - the point is to see what escapes
        raised = exc
    if raised is None:
        return {"outcome": "no_error", "detail": "fault did not surface as an error"}
    name = type(raised).__name__
    if not isinstance(raised, integration.ProviderIntegrationError):
        return {"outcome": "escaped", "error": name, "detail": str(raised)[:160]}
    if name == EXPECTED[fault]:
        return {"outcome": "as_expected", "error": name}
    return {"outcome": "other_integration_error", "error": name, "detail": str(raised)[:160]}


def run_stage_a() -> list[dict[str, Any]]:
    cells = []
    for provider in BUILDERS:
        for operation in OPERATIONS:
            for fault in FAULTS:
                cells.append(
                    {
                        "provider": provider,
                        "operation": operation,
                        "fault": fault,
                        "expected": EXPECTED[fault],
                        **run_cell(provider, operation, fault),
                    }
                )
    return cells
