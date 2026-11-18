"""Capture live provider responses as sanitized, replayable fixtures.

Usage::

    python -m qmill_quantum_provenance.live.capture braket <task-arn> [<task-arn> ...]

For each job the integration retrieval methods are called in the order the
provenance adapters call them. Every outcome, including upstream errors, is
written under ``captures/<provider>/<job>/``:

* ``fixture.json`` -- the integration objects in the fixture format replayed by
  :class:`ReplayIntegrationAdapter`;
* ``native.json`` -- the provider responses the objects were built from;
* ``manifest.json`` -- per-operation outcome, timestamps and mapping notes.

All three are sanitized (secret-like keys redacted, account identifiers masked)
before they are written.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..integration import ProviderAdapter, ProviderIntegrationError
from .sanitize import sanitize

_INTEGRATIONS = {"braket": "qmill_quantum_provenance.live.braket:LiveBraketIntegration"}


def _integration(provider: str) -> ProviderAdapter:
    module_name, _, class_name = _INTEGRATIONS[provider].partition(":")
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)()


def _git_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _slug(job_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", job_id.rsplit("/", 1)[-1])


def capture(provider: str, job_id: str, region: str | None = None) -> dict[str, Any]:
    integration = _integration(provider)
    operations: list[dict[str, Any]] = []
    fixture: dict[str, Any] = {"provider": provider, "external_job_id": job_id, "region": region}

    def run(name: str, call):
        started = datetime.now(UTC)
        try:
            value = call()
            operations.append({"operation": name, "outcome": "ok", "at": started.isoformat()})
            return value
        except ProviderIntegrationError as exc:
            operations.append(
                {
                    "operation": name,
                    "outcome": type(exc).__name__,
                    "message": str(exc),
                    "at": started.isoformat(),
                }
            )
            return None

    handle = integration.get_task(job_id, region=region)
    fixture["region"] = handle.region
    snapshot = run("get_status", lambda: integration.get_status(handle))
    if snapshot is not None:
        fixture["snapshot"] = asdict(snapshot)
        target = snapshot.provider_target_id or snapshot.target_id
        device = (
            run("get_device_details", lambda: integration.get_device_details(target, handle.region))
            if target
            else None
        )
        if device is not None:
            details = asdict(device)
            details["calibration"] = details.pop("calibration_data")
            fixture["device"] = details
        result = run("get_result", lambda: integration.get_result(handle))
        if result is not None:
            fixture["result"] = {
                k: v for k, v in asdict(result).items() if k not in {"provider", "provider_job_id"}
            }

    errors = {
        op["operation"]: {"error": op["outcome"], "message": op.get("message", "")}
        for op in operations
        if op["outcome"] != "ok"
    }
    if errors:
        fixture["upstream_errors"] = errors

    manifest = {
        "provider": provider,
        "external_job_id": job_id,
        "captured_at": datetime.now(UTC).isoformat(),
        "capture_tool_revision": _git_revision(),
        "operations": operations,
        "notes": getattr(integration, "notes", {}),
    }
    return {
        "fixture": sanitize(fixture),
        "native": sanitize(getattr(integration, "native", {})),
        "manifest": sanitize(manifest),
    }


def write_capture(bundle: dict[str, Any], root: Path) -> Path:
    manifest = bundle["manifest"]
    directory = root / manifest["provider"] / _slug(manifest["external_job_id"])
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("fixture", "native", "manifest"):
        (directory / f"{name}.json").write_text(
            json.dumps(bundle[name], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("provider", choices=sorted(_INTEGRATIONS))
    parser.add_argument("job_ids", nargs="+")
    parser.add_argument("--region")
    parser.add_argument("--out", type=Path, default=Path("captures"))
    args = parser.parse_args(argv)
    for job_id in args.job_ids:
        bundle = capture(args.provider, job_id, args.region)
        path = write_capture(bundle, args.out)
        outcomes = ", ".join(
            f"{op['operation']}={op['outcome']}" for op in bundle["manifest"]["operations"]
        )
        print(f"{path}: {outcomes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
