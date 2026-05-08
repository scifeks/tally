"""Unit tests for LlamaCppAdapter.chat()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.ports.llm_provider import LLMAdapterError
from infrastructure.llm.llama_cpp_adapter import LlamaCppAdapter

_URL = "http://localhost:8000"
_MODEL = "llama2"


@pytest.fixture()
def adapter() -> LlamaCppAdapter:
    return LlamaCppAdapter(
        base_url=_URL,
        model=_MODEL,
        timeout_seconds=10,
    )


class TestChat:
    def test_returns_content(self, adapter: LlamaCppAdapter) -> None:
        messages = [{"role": "user", "content": "Hi"}]
        mock_msg = MagicMock(content="Hello back")
        mock_choice = MagicMock(message=mock_msg)
        mock_response = MagicMock(choices=[mock_choice])

        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response
            result = adapter.chat(messages)

        assert result == "Hello back"

    def test_uses_v1_base_url(self, adapter: LlamaCppAdapter) -> None:
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_resp = MagicMock(choices=[MagicMock(message=MagicMock(content="x"))])
            mock_client.chat.completions.create.return_value = mock_resp
            adapter.chat([{"role": "user", "content": "Hi"}])

        call_kwargs = mock_oai.OpenAI.call_args[1]
        assert call_kwargs["base_url"] == f"{_URL}/v1"
        assert call_kwargs["api_key"] == "not-needed"

    def test_wraps_errors_in_llm_adapter_error(self, adapter: LlamaCppAdapter) -> None:
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.side_effect = RuntimeError("fail")
            with pytest.raises(LLMAdapterError):
                adapter.chat([{"role": "user", "content": "Hi"}])

    def test_model_property(self, adapter: LlamaCppAdapter) -> None:
        assert adapter.model == _MODEL

    def test_returns_empty_string_on_none_content(
        self, adapter: LlamaCppAdapter
    ) -> None:
        mock_resp = MagicMock(choices=[MagicMock(message=MagicMock(content=None))])
        with patch("infrastructure.llm.llama_cpp_adapter.openai") as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp
            result = adapter.chat([{"role": "user", "content": "Hi"}])
        assert result == ""
