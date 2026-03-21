"""Unit tests for ClaudeAdapter.complete."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.llm.claude_adapter import ClaudeAdapter

_MODEL = "claude-opus-4-5"
_API_KEY = "test-key-abc"


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


class TestComplete:
    def test_delegates_to_chat(self, adapter: ClaudeAdapter) -> None:
        with patch.object(adapter, "chat", return_value="result") as mock_chat:
            out = adapter.complete("my prompt", temperature=0.3)
        mock_chat.assert_called_once_with(
            [{"role": "user", "content": "my prompt"}], temperature=0.3
        )
        assert out == "result"
