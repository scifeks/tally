"""Contract tests for the LLMProvider abstract base class.

Verifies that any concrete subclass missing one of the four abstract
methods (is_available, complete, chat, stream_chat) cannot be
instantiated. This is the ABC-level guard that keeps adapters honest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from core.llm.base import LLMProvider


class _AsyncEmpty:
    """Async iterator that yields nothing."""

    def __aiter__(self) -> _AsyncEmpty:
        return self

    async def __anext__(self) -> str:
        raise StopAsyncIteration


class _Complete(LLMProvider):
    """Reference complete implementation used as a baseline."""

    @property
    def model(self) -> str:
        return "test-model"

    def is_available(self) -> bool:
        return True

    def complete(self, _prompt: str, **_kwargs: Any) -> str:
        return ""

    def chat(self, _messages: list[dict[str, str]], **_kwargs: Any) -> str:
        return ""

    def stream_chat(
        self,
        _messages: list[dict[str, str]],
        **_kwargs: Any,
    ) -> AsyncIterator[str]:
        return _AsyncEmpty()


def test_complete_subclass_can_instantiate() -> None:
    _Complete()


def test_missing_stream_chat_cannot_instantiate() -> None:
    class _NoStream(LLMProvider):
        @property
        def model(self) -> str:
            return "m"

        def is_available(self) -> bool:
            return True

        def complete(self, _prompt: str, **_kwargs: Any) -> str:
            return ""

        def chat(self, _messages: list[dict[str, str]], **_kwargs: Any) -> str:
            return ""

    with pytest.raises(TypeError, match="stream_chat"):
        _NoStream()  # type: ignore[abstract]


def test_missing_chat_cannot_instantiate() -> None:
    class _NoChat(LLMProvider):
        @property
        def model(self) -> str:
            return "m"

        def is_available(self) -> bool:
            return True

        def complete(self, _prompt: str, **_kwargs: Any) -> str:
            return ""

        def stream_chat(
            self,
            _messages: list[dict[str, str]],
            **_kwargs: Any,
        ) -> AsyncIterator[str]:
            return _AsyncEmpty()

    with pytest.raises(TypeError, match="chat"):
        _NoChat()  # type: ignore[abstract]


def test_stream_chat_returns_async_iterator() -> None:
    """Calling stream_chat must produce an async iterator (not a coroutine)."""
    provider = _Complete()
    result = provider.stream_chat([{"role": "user", "content": "hi"}])
    assert hasattr(result, "__aiter__")
    assert hasattr(result, "__anext__")
