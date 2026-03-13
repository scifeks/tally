"""Abstract base class for LLM provider adapters."""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Interface all LLM adapters must implement."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is reachable and ready."""
        ...

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Generate a completion for a single prompt string."""
        ...

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Generate a response from a list of chat messages."""
        ...

    @abstractmethod
    def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Return a float embedding vector for the given text."""
        ...
