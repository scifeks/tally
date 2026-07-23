"""Unit tests for OpenAIAdapter.chat."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import openai
import pytest

from application.ports.llm_provider import LLMAdapterError
from infrastructure.llm.openai_adapter import OpenAIAdapter

_MODEL = "gpt-4o"
_API_KEY = "sk-test-abc"


def _mock_response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = _MODEL
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 5
    return resp


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


@pytest.fixture()
def mock_client(adapter: OpenAIAdapter) -> MagicMock:
    """Return adapter._client as a MagicMock (its true runtime type)."""
    return cast(MagicMock, adapter._client)


class TestChat:
    def test_system_message_passed_through(
        self, adapter: OpenAIAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        adapter.chat(
            [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "hello"},
            ]
        )
        _, call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs["messages"]
        assert any(m["role"] == "system" for m in messages)

    def test_returns_response_text(
        self, adapter: OpenAIAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.chat.completions.create.return_value = _mock_response("hello world")
        result = adapter.chat([{"role": "user", "content": "hi"}])
        assert result == "hello world"

    def test_num_predict_used_as_max_tokens(
        self, adapter: OpenAIAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        adapter.chat([{"role": "user", "content": "q"}], num_predict=256)
        _, call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs["max_tokens"] == 256

    def test_max_tokens_override(
        self, adapter: OpenAIAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        adapter.chat([{"role": "user", "content": "q"}], max_tokens=1024)
        _, call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs["max_tokens"] == 1024

    def test_api_error_wrapped(
        self, adapter: OpenAIAdapter, mock_client: MagicMock
    ) -> None:
        exc = openai.APIError(
            message="test error",
            request=MagicMock(),
            body=None,
        )
        mock_client.chat.completions.create.side_effect = exc
        with pytest.raises(LLMAdapterError):
            adapter.chat([{"role": "user", "content": "q"}])

    def test_complete_delegates_to_chat(
        self, adapter: OpenAIAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        result = adapter.complete("test prompt")
        assert result == "ok"
        _, call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "test prompt"
