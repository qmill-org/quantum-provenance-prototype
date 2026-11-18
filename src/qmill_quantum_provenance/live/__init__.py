"""Live provider retrieval for held-out validation.

The modules in this package implement the integration :class:`ProviderAdapter`
retrieval seam against real provider services, and capture the responses as
sanitized fixtures that replay through :class:`ReplayIntegrationAdapter`.
Provider SDKs are optional dependencies (``pip install .[live]``).
"""
