"""Unit tests for LlamaCppAdapter.stream_chat()."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.ports.llm_provider import LLMAdapterError
from infrastructure.llm.llama_cpp_adapter import LlamaCppAdapter

_URL = "http://localhost:8000"
_MODEL = "llama2"


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    for x in items:
        yield x


def _make_chunk(content: str | None) -> MagicMock:
    delta = MagicMock()
    delta.content = content
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


@pytest.fixture()
def adapter() -> LlamaCppAdapter:
    return LlamaCppAdapter(base_url=_URL, model=_MODEL, timeout_seconds=10)


class TestStreamChat:
    async def test_yields_content_chunks(self, adapter: LlamaCppAdapter) -> None:
        chunks = [_make_chunk(c) for c in ["Hi", "!"]]
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.AsyncOpenAI.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=_aiter(chunks))
            received = [
                c
                async for c in adapter.stream_chat([{"role": "user", "content": "Hi"}])
            ]
        assert received == ["Hi", "!"]

    async def test_skips_empty_deltas(self, adapter: LlamaCppAdapter) -> None:
        chunks = [
            _make_chunk("A"),
            _make_chunk(None),
            _make_chunk(""),
            _make_chunk("B"),
        ]
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.AsyncOpenAI.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=_aiter(chunks))
            received = [
                c
                async for c in adapter.stream_chat([{"role": "user", "content": "Hi"}])
            ]
        assert received == ["A", "B"]

    async def test_wraps_errors(self, adapter: LlamaCppAdapter) -> None:
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.AsyncOpenAI.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(
                side_effect=RuntimeError("fail")
            )

            with pytest.raises(LLMAdapterError):
                async for _ in adapter.stream_chat([{"role": "user", "content": "Hi"}]):
                    pass

    async def test_uses_async_openai_client(self, adapter: LlamaCppAdapter) -> None:
        chunks = [_make_chunk("x")]
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.AsyncOpenAI.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=_aiter(chunks))
            async for _ in adapter.stream_chat([{"role": "user", "content": "Hi"}]):
                pass

        call_kwargs = mock_oai.AsyncOpenAI.call_args[1]
        assert call_kwargs["base_url"] == f"{_URL}/v1"
        assert call_kwargs["api_key"] == "not-needed"
