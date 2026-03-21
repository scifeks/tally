"""Unit tests for ClaudeAdapter.is_available."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.llm.claude_adapter import ClaudeAdapter

_MODEL = "claude-opus-4-5"
_API_KEY = "test-key-abc"


class TestIsAvailable:
    def test_returns_true_when_key_set(self) -> None:
        with patch("core.llm.claude_adapter.anthropic.Anthropic"):
            adapter = ClaudeAdapter(api_key=_API_KEY, model=_MODEL, max_tokens=512)
        assert adapter.is_available() is True

    def test_returns_false_when_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("core.llm.claude_adapter.anthropic.Anthropic"):
            adapter = ClaudeAdapter(api_key="", model=_MODEL, max_tokens=512)
        assert adapter.is_available() is False

    def test_env_var_satisfies_availability(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        with patch("core.llm.claude_adapter.anthropic.Anthropic"):
            adapter = ClaudeAdapter(api_key="", model=_MODEL, max_tokens=512)
        assert adapter.is_available() is True
