"""Unit tests for ClaudeAdapter — all SDK calls mocked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from core.llm.base import LLMAdapterError
from core.llm.claude_adapter import ClaudeAdapter
from core.llm.factory import get_llm_provider

_MODEL = "claude-opus-4-5"
_API_KEY = "test-key-abc"


def _make_api_status_error(
    cls: type[anthropic.APIStatusError], status_code: int
) -> anthropic.APIStatusError:
    return cls(
        message="test",
        response=MagicMock(status_code=status_code),
        body=None,
    )


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


@pytest.fixture()
def mock_client(adapter: ClaudeAdapter) -> MagicMock:
    """Return adapter._client as a MagicMock (its true runtime type)."""
    return cast(MagicMock, adapter._client)


def _mock_response(text: str) -> MagicMock:
    content_block = MagicMock()
    content_block.text = text
    resp = MagicMock()
    resp.content = [content_block]
    resp.model = _MODEL
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    return resp


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


class TestChat:
    def test_successful_chat(
        self, adapter: ClaudeAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.messages.create.return_value = _mock_response("hello!")
        result = adapter.chat([{"role": "user", "content": "hi"}])
        assert result == "hello!"

    def test_system_message_extracted(
        self, adapter: ClaudeAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.messages.create.return_value = _mock_response("ok")
        adapter.chat(
            [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "hello"},
            ]
        )
        _, call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs["system"] == "You are a helpful assistant."
        for msg in call_kwargs["messages"]:
            assert msg["role"] != "system"

    def test_num_predict_used_as_max_tokens(
        self, adapter: ClaudeAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.messages.create.return_value = _mock_response("ok")
        adapter.chat(
            [{"role": "user", "content": "q"}],
            num_predict=256,
        )
        _, call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs["max_tokens"] == 256

    def test_temperature_forwarded(
        self, adapter: ClaudeAdapter, mock_client: MagicMock
    ) -> None:
        mock_client.messages.create.return_value = _mock_response("ok")
        adapter.chat(
            [{"role": "user", "content": "q"}],
            temperature=0.7,
        )
        _, call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs["temperature"] == 0.7

    def test_empty_messages_raises(self, adapter: ClaudeAdapter) -> None:
        with pytest.raises(LLMAdapterError, match="non-system message"):
            adapter.chat([{"role": "system", "content": "sys only"}])

    def test_invalid_role_raises(self, adapter: ClaudeAdapter) -> None:
        with pytest.raises(LLMAdapterError, match="Invalid message role"):
            adapter.chat([{"role": "tool", "content": "bad"}])

    def test_auth_error_raises_adapter_error(
        self, adapter: ClaudeAdapter, mock_client: MagicMock
    ) -> None:
        exc = _make_api_status_error(anthropic.AuthenticationError, 401)
        mock_client.messages.create.side_effect = exc
        with pytest.raises(LLMAdapterError):
            adapter.chat([{"role": "user", "content": "q"}])

    def test_rate_limit_raises_adapter_error(
        self, adapter: ClaudeAdapter, mock_client: MagicMock
    ) -> None:
        exc = _make_api_status_error(anthropic.RateLimitError, 429)
        mock_client.messages.create.side_effect = exc
        with pytest.raises(LLMAdapterError):
            adapter.chat([{"role": "user", "content": "q"}])


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------


class TestComplete:
    def test_delegates_to_chat(self, adapter: ClaudeAdapter) -> None:
        with patch.object(adapter, "chat", return_value="result") as mock_chat:
            out = adapter.complete("my prompt", temperature=0.3)
        mock_chat.assert_called_once_with(
            [{"role": "user", "content": "my prompt"}], temperature=0.3
        )
        assert out == "result"


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


class TestEmbed:
    def test_raises_not_implemented(self, adapter: ClaudeAdapter) -> None:
        with pytest.raises(NotImplementedError):
            adapter.embed("some text")


# ---------------------------------------------------------------------------
# factory integration
# ---------------------------------------------------------------------------


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "chat_llm_provider": "claude",
        "enrichment_llm_provider": "ollama",
        "report_llm_provider": "ollama",
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "qwen3:14b",
            "embedding_model": "nomic-embed-text:latest",
        },
        "claude": {
            "api_key": _API_KEY,
            "model": _MODEL,
            "max_tokens": 512,
            "timeout_seconds": 10,
        },
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestFactory:
    def test_factory_resolves_claude(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        with patch("core.llm.claude_adapter.anthropic.Anthropic"):
            provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, ClaudeAdapter)

    def test_factory_unknown_provider_raises(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"chat_llm_provider": "unknown_provider"})
        with pytest.raises(ValueError, match="unknown_provider"):
            get_llm_provider("chat", tmp_path)
