"""Unit tests for OpenAIAdapter.is_available."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from infrastructure.llm.openai_adapter import OpenAIAdapter

_MODEL = "gpt-4o"
_API_KEY = "sk-test-abc"


class TestIsAvailable:
    def test_returns_true_when_key_set(self) -> None:
        with patch("infrastructure.llm.openai_adapter.openai.OpenAI"):
            adapter = OpenAIAdapter(api_key=_API_KEY, model=_MODEL, max_tokens=512)
        assert adapter.is_available() is True

    def test_returns_false_when_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch("infrastructure.llm.openai_adapter.openai.OpenAI"):
            adapter = OpenAIAdapter(api_key="", model=_MODEL, max_tokens=512)
        assert adapter.is_available() is False

    def test_env_var_satisfies_availability(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        with patch("infrastructure.llm.openai_adapter.openai.OpenAI"):
            adapter = OpenAIAdapter(api_key="", model=_MODEL, max_tokens=512)
        assert adapter.is_available() is True
