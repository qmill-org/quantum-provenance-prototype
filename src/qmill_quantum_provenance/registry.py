"""Registry for provenance adapters.

Separate from the integration ``get_provider_adapter`` factory so that adding a
provenance provider never touches the submission/execution path. Adapters are
registered by factory and instantiated lazily; instances are cached.
"""

from __future__ import annotations

from collections.abc import Callable

from .adapter import ProvenanceAdapter


class ProvenanceAdapterRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ProvenanceAdapter]] = {}
        self._instances: dict[str, ProvenanceAdapter] = {}

    def register(
        self,
        provider: str,
        factory: Callable[[], ProvenanceAdapter],
        *,
        replace: bool = False,
    ) -> None:
        if provider in self._factories and not replace:
            raise ValueError(f"Provenance adapter already registered: {provider}")
        self._factories[provider] = factory
        self._instances.pop(provider, None)

    def get(self, provider: str) -> ProvenanceAdapter:
        if provider not in self._factories:
            raise KeyError(provider)
        if provider not in self._instances:
            self._instances[provider] = self._factories[provider]()
        return self._instances[provider]

    def providers(self) -> list[str]:
        return sorted(self._factories)

    def is_registered(self, provider: str) -> bool:
        return provider in self._factories


def default_registry() -> ProvenanceAdapterRegistry:
    """Registry with the providers implemented so far (Braket, IBM, IonQ)."""

    registry = ProvenanceAdapterRegistry()

    def _braket() -> ProvenanceAdapter:
        from .adapters.braket import BraketProvenanceAdapter

        return BraketProvenanceAdapter()

    def _ibm() -> ProvenanceAdapter:
        from .adapters.ibm import IBMProvenanceAdapter

        return IBMProvenanceAdapter()

    def _ionq() -> ProvenanceAdapter:
        from .adapters.ionq import IonQProvenanceAdapter

        return IonQProvenanceAdapter()

    registry.register("braket", _braket)
    registry.register("ibm", _ibm)
    registry.register("ionq", _ionq)
    return registry


__all__ = ["ProvenanceAdapterRegistry", "default_registry"]
