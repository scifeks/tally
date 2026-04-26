"""Unit tests for OllamaAdapter.stream_chat."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm.base import LLMAdapterError
from core.llm.ollama_adapter import OllamaAdapter

_URL = "http://localhost:11434"
_MODEL = "qwen3:14b"


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    for x in items:
        yield x


def _make_object_chunk(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    chunk = MagicMock()
    chunk.message = msg
    return chunk


def _make_dict_chunk(content: str) -> dict[str, Any]:
    return {"message": {"content": content}}


@pytest.fixture()
def adapter() -> OllamaAdapter:
    return OllamaAdapter(base_url=_URL, model=_MODEL, timeout_seconds=10)


class TestStreamChat:
    async def test_yields_object_chunks_in_order(self, adapter: OllamaAdapter) -> None:
        chunks = [_make_object_chunk(c) for c in ["Hel", "lo, ", "world"]]
        with patch("ollama.AsyncClient") as MockAsync:
            MockAsync.return_value.chat = AsyncMock(return_value=_aiter(chunks))
            received = [
                c
                async for c in adapter.stream_chat([{"role": "user", "content": "hi"}])
            ]
        assert received == ["Hel", "lo, ", "world"]

    async def test_yields_dict_chunks_in_order(self, adapter: OllamaAdapter) -> None:
        chunks = [_make_dict_chunk(c) for c in ["a", "b", "c"]]
        with patch("ollama.AsyncClient") as MockAsync:
            MockAsync.return_value.chat = AsyncMock(return_value=_aiter(chunks))
            received = [
                c
                async for c in adapter.stream_chat([{"role": "user", "content": "hi"}])
            ]
        assert received == ["a", "b", "c"]

    async def test_empty_chunks_skipped(self, adapter: OllamaAdapter) -> None:
        chunks = [
            _make_object_chunk("hi"),
            _make_object_chunk(""),
            _make_object_chunk(" there"),
        ]
        with patch("ollama.AsyncClient") as MockAsync:
            MockAsync.return_value.chat = AsyncMock(return_value=_aiter(chunks))
            received = [
                c
                async for c in adapter.stream_chat([{"role": "user", "content": "hi"}])
            ]
        assert received == ["hi", " there"]

    async def test_kwargs_merged_into_options(self, adapter: OllamaAdapter) -> None:
        with patch("ollama.AsyncClient") as MockAsync:
            mock_chat = AsyncMock(return_value=_aiter([]))
            MockAsync.return_value.chat = mock_chat
            async for _ in adapter.stream_chat(
                [{"role": "user", "content": "q"}],
                temperature=0.5,
                num_predict=100,
            ):
                pass
        _, call_kwargs = mock_chat.call_args
        assert call_kwargs["stream"] is True
        assert call_kwargs["options"] == {"temperature": 0.5, "num_predict": 100}

    async def test_num_ctx_added_to_options(self) -> None:
        adapter = OllamaAdapter(base_url=_URL, model=_MODEL, num_ctx=8192)
        with patch("ollama.AsyncClient") as MockAsync:
            mock_chat = AsyncMock(return_value=_aiter([]))
            MockAsync.return_value.chat = mock_chat
            async for _ in adapter.stream_chat([{"role": "user", "content": "q"}]):
                pass
        _, call_kwargs = mock_chat.call_args
        assert call_kwargs["options"]["num_ctx"] == 8192

    async def test_exception_wrapped_as_adapter_error(
        self, adapter: OllamaAdapter
    ) -> None:
        with patch("ollama.AsyncClient") as MockAsync:
            MockAsync.return_value.chat = AsyncMock(
                side_effect=RuntimeError("connection refused")
            )
            with pytest.raises(LLMAdapterError, match="connection refused"):
                async for _ in adapter.stream_chat([{"role": "user", "content": "q"}]):
                    pass

    async def test_iteration_error_wrapped(self, adapter: OllamaAdapter) -> None:
        async def _broken() -> AsyncIterator[Any]:
            yield _make_object_chunk("ok")
            raise RuntimeError("stream broke")

        with patch("ollama.AsyncClient") as MockAsync:
            MockAsync.return_value.chat = AsyncMock(return_value=_broken())
            with pytest.raises(LLMAdapterError, match="stream broke"):
                async for _ in adapter.stream_chat([{"role": "user", "content": "q"}]):
                    pass
