"""Embedding provider port contract."""

from __future__ import annotations

from typing import Any, Protocol


class EmbeddingAdapterError(Exception):
    """Raised by embedding adapters for provider-specific errors."""


class EmbeddingProvider(Protocol):
    """Interface all embedding adapters must implement."""

    def is_available(self) -> bool:
        """Return True if the provider is reachable and ready."""
        ...

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Return a float embedding vector for the given text."""
        ...
