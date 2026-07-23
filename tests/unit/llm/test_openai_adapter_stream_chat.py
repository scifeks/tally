"""Unit tests for OpenAIAdapter.stream_chat."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from application.ports.llm_provider import LLMAdapterError
from infrastructure.llm.openai_adapter import OpenAIAdapter

_MODEL = "gpt-4o"
_API_KEY = "sk-test-abc"
_ASYNC_PATCH = "infrastructure.llm.openai_adapter.openai.AsyncOpenAI"


async def _aiter(items: list[str | None]) -> AsyncIterator[str | None]:
    for x in items:
        yield x


class _FakeChunk:
    """Fake of a chunk from the OpenAI streaming API."""

    def __init__(self, text: str | None) -> None:
        self.choices = [MagicMock()]
        self.choices[0].delta.content = text


class _FakeAsyncStream:
    """Async iterator over fake OpenAI stream chunks."""

    def __init__(self, chunks: list[str | None]) -> None:
        self._chunks = [_FakeChunk(c) for c in chunks]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


@pytest.fixture()
def adapter() -> OpenAIAdapter:
    with patch("infrastructure.llm.openai_adapter.openai.OpenAI"):
        inst = OpenAIAdapter(
            api_key=_API_KEY,
            model=_MODEL,
            max_tokens=512,
            timeout_seconds=10,
        )
    return inst


class TestStreamChat:
    async def test_yields_chunks_in_order(self, adapter: OpenAIAdapter) -> None:
        stream = _FakeAsyncStream(["Hel", "lo, ", "world"])
        with patch(_ASYNC_PATCH) as MockAsync:
            MockAsync.return_value.chat.completions.create = AsyncMock(
                return_value=stream
            )
            received = [
                chunk
                async for chunk in adapter.stream_chat(
                    [{"role": "user", "content": "hi"}]
                )
            ]
        assert received == ["Hel", "lo, ", "world"]

    async def test_system_message_passed_through(self, adapter: OpenAIAdapter) -> None:
        stream = _FakeAsyncStream(["ok"])
        with patch(_ASYNC_PATCH) as MockAsync:
            create_call = AsyncMock(return_value=stream)
            MockAsync.return_value.chat.completions.create = create_call
            async for _ in adapter.stream_chat(
                [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "hello"},
                ]
            ):
                pass
        _, call_kwargs = create_call.call_args
        messages = call_kwargs["messages"]
        assert any(m["role"] == "system" for m in messages)

    async def test_num_predict_mapped_to_max_tokens(
        self, adapter: OpenAIAdapter
    ) -> None:
        stream = _FakeAsyncStream(["ok"])
        with patch(_ASYNC_PATCH) as MockAsync:
            create_call = AsyncMock(return_value=stream)
            MockAsync.return_value.chat.completions.create = create_call
            async for _ in adapter.stream_chat(
                [{"role": "user", "content": "q"}],
                num_predict=128,
            ):
                pass
        _, call_kwargs = create_call.call_args
        assert call_kwargs["max_tokens"] == 128

    async def test_api_error_wrapped(self, adapter: OpenAIAdapter) -> None:
        exc = openai.APIError(
            message="test error",
            request=MagicMock(),
            body=None,
        )
        with patch(_ASYNC_PATCH) as MockAsync:
            MockAsync.return_value.chat.completions.create = AsyncMock(side_effect=exc)
            with pytest.raises(LLMAdapterError):
                async for _ in adapter.stream_chat([{"role": "user", "content": "q"}]):
                    pass

    async def test_skips_none_content(self, adapter: OpenAIAdapter) -> None:
        stream = _FakeAsyncStream(["Hello", None, " ", None, "world"])
        with patch(_ASYNC_PATCH) as MockAsync:
            MockAsync.return_value.chat.completions.create = AsyncMock(
                return_value=stream
            )
            received = [
                chunk
                async for chunk in adapter.stream_chat(
                    [{"role": "user", "content": "hi"}]
                )
            ]
        assert received == ["Hello", " ", "world"]
