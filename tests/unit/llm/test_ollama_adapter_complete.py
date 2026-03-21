"""Unit tests for OllamaAdapter.complete."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.llm.ollama_adapter import OllamaAdapter

_URL = "http://localhost:11434"
_MODEL = "qwen3:14b"


@pytest.fixture()
def adapter() -> OllamaAdapter:
    return OllamaAdapter(
        base_url=_URL,
        model=_MODEL,
        timeout_seconds=10,
    )


class TestComplete:
    def test_delegates_to_chat(self, adapter: OllamaAdapter) -> None:
        with patch.object(adapter, "chat", return_value="result") as mock_chat:
            out = adapter.complete("my prompt", temperature=0.3)
        mock_chat.assert_called_once_with(
            [{"role": "user", "content": "my prompt"}], temperature=0.3
        )
        assert out == "result"
