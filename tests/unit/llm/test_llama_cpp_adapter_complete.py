"""Unit tests for LlamaCppAdapter.complete()."""

from __future__ import annotations

from unittest.mock import patch

import pytest

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


class TestComplete:
    def test_delegates_to_chat(self, adapter: LlamaCppAdapter) -> None:
        with patch.object(adapter, "chat", return_value="Result") as mock_chat:
            result = adapter.complete("Some prompt")

        assert result == "Result"
        messages = mock_chat.call_args[0][0]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Some prompt"
