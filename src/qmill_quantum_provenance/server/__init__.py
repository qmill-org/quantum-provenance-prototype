"""Reference HTTP service for the provenance contract (protocols/http-service.md)."""

from .app import create_app

__all__ = ["create_app"]
