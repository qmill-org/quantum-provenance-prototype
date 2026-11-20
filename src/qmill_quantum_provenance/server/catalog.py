"""Replay mode: serve the committed captures as if they were the providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..integration import JobNotFoundError, TaskHandle
from ..replay import ReplayIntegrationAdapter


class CaptureCatalog:
    def __init__(self, captures: str | Path) -> None:
        self._fixtures: dict[tuple[str, str], dict[str, Any]] = {}
        for path in sorted(Path(captures).glob("*/*/fixture.json")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            self._fixtures[(fixture["provider"], str(fixture["external_job_id"]))] = fixture

    def get(self, provider: str, external_job_id: str) -> dict[str, Any] | None:
        return self._fixtures.get((provider, external_job_id))


class CatalogIntegration(ReplayIntegrationAdapter):
    """A replay integration that picks the capture by provider job id."""

    def __init__(self, provider: str, catalog: CaptureCatalog) -> None:
        super().__init__({"provider": provider})
        self._catalog = catalog

    def get_task(self, provider_job_id: str, region: str | None = None) -> TaskHandle:
        fixture = self._catalog.get(self._provider, provider_job_id)
        if fixture is None:
            raise JobNotFoundError(f"No capture for {self._provider} job")
        self._fixture = fixture
        return super().get_task(provider_job_id, region)
