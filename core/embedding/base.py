"""Abstract base class for embedding provider adapters."""

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingAdapterError(Exception):
    """Raised by embedding adapters for provider-specific errors."""


class EmbeddingProvider(ABC):
    """Interface all embedding adapters must implement."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is reachable and ready."""
        ...

    @abstractmethod
    def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Return a float embedding vector for the given text."""
        ...
