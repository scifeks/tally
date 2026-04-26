"""Unit tests for ClaudeAdapter.stream_chat."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from core.llm.base import LLMAdapterError
from core.llm.claude_adapter import ClaudeAdapter

_MODEL = "claude-opus-4-5"
_API_KEY = "test-key-abc"


async def _aiter(items: list[str]) -> AsyncIterator[str]:
    for x in items:
        yield x


class _FakeStream:
    """Fake of the object returned by ``messages.stream(...).__aenter__``."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return _aiter(self._chunks)


class _FakeStreamCtx:
    """Async context manager wrapping a _FakeStream."""

    def __init__(self, chunks: list[str]) -> None:
        self._stream = _FakeStream(chunks)
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> _FakeStream:
        self.entered = True
        return self._stream

    async def __aexit__(self, *_: object) -> bool:
        self.exited = True
        return False


def _make_api_status_error(
    cls: type[anthropic.APIStatusError], status_code: int
) -> anthropic.APIStatusError:
    return cls(
        message="test",
        response=MagicMock(status_code=status_code),
        body=None,
    )


@pytest.fixture()
def adapter() -> ClaudeAdapter:
    with patch("core.llm.claude_adapter.anthropic.Anthropic"):
        inst = ClaudeAdapter(
            api_key=_API_KEY,
            model=_MODEL,
            max_tokens=512,
            timeout_seconds=10,
        )
    return inst


class TestStreamChat:
    async def test_yields_chunks_in_order(self, adapter: ClaudeAdapter) -> None:
        ctx = _FakeStreamCtx(["Hel", "lo, ", "world"])
        with patch("core.llm.claude_adapter.anthropic.AsyncAnthropic") as MockAsync:
            MockAsync.return_value.messages.stream.return_value = ctx
            received = [
                chunk
                async for chunk in adapter.stream_chat(
                    [{"role": "user", "content": "hi"}]
                )
            ]
        assert received == ["Hel", "lo, ", "world"]
        assert ctx.entered and ctx.exited

    async def test_system_message_extracted(self, adapter: ClaudeAdapter) -> None:
        ctx = _FakeStreamCtx(["ok"])
        with patch("core.llm.claude_adapter.anthropic.AsyncAnthropic") as MockAsync:
            stream_call = MockAsync.return_value.messages.stream
            stream_call.return_value = ctx
            async for _ in adapter.stream_chat(
                [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "hello"},
                ]
            ):
                pass
        _, call_kwargs = stream_call.call_args
        assert call_kwargs["system"] == "You are helpful."
        for msg in call_kwargs["messages"]:
            assert msg["role"] != "system"

    async def test_kwargs_forwarded(self, adapter: ClaudeAdapter) -> None:
        ctx = _FakeStreamCtx(["ok"])
        with patch("core.llm.claude_adapter.anthropic.AsyncAnthropic") as MockAsync:
            stream_call = MockAsync.return_value.messages.stream
            stream_call.return_value = ctx
            async for _ in adapter.stream_chat(
                [{"role": "user", "content": "q"}],
                temperature=0.5,
                num_predict=128,
            ):
                pass
        _, call_kwargs = stream_call.call_args
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 128
        assert call_kwargs["model"] == _MODEL

    async def test_empty_messages_raises(self, adapter: ClaudeAdapter) -> None:
        with pytest.raises(LLMAdapterError, match="non-system message"):
            async for _ in adapter.stream_chat(
                [{"role": "system", "content": "sys only"}]
            ):
                pass

    async def test_invalid_role_raises(self, adapter: ClaudeAdapter) -> None:
        with pytest.raises(LLMAdapterError, match="Invalid message role"):
            async for _ in adapter.stream_chat([{"role": "tool", "content": "x"}]):
                pass

    async def test_api_error_wrapped(self, adapter: ClaudeAdapter) -> None:
        exc = _make_api_status_error(anthropic.AuthenticationError, 401)
        with patch("core.llm.claude_adapter.anthropic.AsyncAnthropic") as MockAsync:
            MockAsync.return_value.messages.stream.side_effect = exc
            with pytest.raises(LLMAdapterError):
                async for _ in adapter.stream_chat([{"role": "user", "content": "q"}]):
                    pass

    async def test_aclose_propagates_to_context(self, adapter: ClaudeAdapter) -> None:
        """Closing the generator must run the SDK's __aexit__ for cleanup."""
        ctx = _FakeStreamCtx(["a", "b", "c", "d"])
        with patch("core.llm.claude_adapter.anthropic.AsyncAnthropic") as MockAsync:
            MockAsync.return_value.messages.stream.return_value = ctx
            gen = cast(
                AsyncIterator[str],
                adapter.stream_chat([{"role": "user", "content": "q"}]),
            )
            first = await gen.__anext__()
            assert first == "a"
            await gen.aclose()  # type: ignore[attr-defined]
        assert ctx.entered and ctx.exited
