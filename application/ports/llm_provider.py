"""Language-model adapter contract.

Adapters:
  infrastructure/llm/claude_adapter.py     (Anthropic Messages API)
  infrastructure/llm/ollama_adapter.py     (local Ollama HTTP)
  infrastructure/llm/llama_cpp_adapter.py  (local llama.cpp HTTP)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class LLMAdapterError(Exception):
    """Raised by LLM adapters when a provider-specific error occurs.

    Wraps SDK-specific exceptions (e.g. anthropic.APIError) so callers
    never see provider SDK types leak across the adapter boundary.
    """


class LLMProvider(Protocol):
    """Interface all LLM adapters must implement."""

    @property
    def model(self) -> str:
        """The provider's configured model identifier (e.g. ``llama3.1:8b``)."""
        ...

    def is_available(self) -> bool:
        """Return True if the provider is reachable and ready."""
        ...

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Generate a completion for a single prompt string."""
        ...

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Generate a response from a list of chat messages."""
        ...

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream the model's reply as already-decoded UTF-8 text chunks.

        Implementations MUST be async generators (``async def`` with
        ``yield``). Each yielded chunk is a plain UTF-8 string fragment
        produced by the provider's streaming API; chunks are not
        word-aligned and may include mid-word fragments. Callers are
        responsible for any presentation buffering.

        Cancellation flows through standard ``asyncio`` task cancellation:
        when the consumer calls ``aclose()`` on the iterator (or its
        owning task is cancelled), implementations MUST close the
        underlying provider stream. Errors raised by the provider MUST
        be wrapped in :class:`LLMAdapterError` before propagation.
        """
        ...
