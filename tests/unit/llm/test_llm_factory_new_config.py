"""Unit tests for get_llm_provider with new config schema."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.llm.claude_adapter import ClaudeAdapter
from infrastructure.llm.factory import get_llm_provider
from infrastructure.llm.llama_cpp_adapter import LlamaCppAdapter
from infrastructure.llm.ollama_adapter import OllamaAdapter


def _write_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "qwen3:14b",
            "timeout_seconds": 60,
            "num_ctx": 8192,
        },
        "llama_cpp": {
            "base_url": "http://localhost:8000",
            "model": "llama2",
            "timeout_seconds": 90,
        },
        "claude": {
            "api_key": "sk-test",
            "model": "claude-opus-4-5",
            "max_tokens": 2048,
            "timeout_seconds": 60,
        },
        "chat_inference": {"provider": "ollama"},
        "enrichment_inference": {"provider": "ollama"},
        "report_inference": {"provider": "ollama"},
        "embedding_inference": {"provider": "ollama"},
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestLLMFactoryNewConfig:
    def test_chat_returns_ollama(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_enrichment_returns_ollama(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        provider = get_llm_provider("enrichment", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_report_returns_ollama(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_chat_returns_claude(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {"chat_inference": {"provider": "claude"}},
        )
        with patch("infrastructure.llm.claude_adapter.anthropic.Anthropic"):
            provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, ClaudeAdapter)

    def test_report_returns_llama_cpp(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {"report_inference": {"provider": "llama_cpp"}},
        )
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, LlamaCppAdapter)

    def test_model_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "chat_inference": {
                    "provider": "ollama",
                    "model": "qwen2.5:32b",
                }
            },
        )
        provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider.model == "qwen2.5:32b"

    def test_timeout_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "report_inference": {
                    "provider": "ollama",
                    "timeout_seconds": 180,
                }
            },
        )
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._timeout == 180

    def test_num_ctx_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "enrichment_inference": {
                    "provider": "ollama",
                    "num_ctx": 4096,
                }
            },
        )
        provider = get_llm_provider("enrichment", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._num_ctx == 4096

    def test_max_tokens_override_claude(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "chat_inference": {
                    "provider": "claude",
                    "max_tokens": 4096,
                }
            },
        )
        with patch("infrastructure.llm.claude_adapter.anthropic.Anthropic"):
            provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, ClaudeAdapter)
        assert provider._max_tokens == 4096

    def test_missing_feature_config_raises(self, tmp_path: Path) -> None:
        _write_config(tmp_path, {"chat_inference": None})
        with pytest.raises(ValueError, match="chat_inference"):
            get_llm_provider("chat", tmp_path)

    def test_missing_provider_config_raises(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {"chat_inference": {"provider": "nonexistent"}},
        )
        with pytest.raises(ValueError, match="nonexistent"):
            get_llm_provider("chat", tmp_path)

    def test_roles_independent(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "chat_inference": {"provider": "claude"},
                "enrichment_inference": {"provider": "ollama"},
                "report_inference": {"provider": "llama_cpp"},
            },
        )
        with patch("infrastructure.llm.claude_adapter.anthropic.Anthropic"):
            chat = get_llm_provider("chat", tmp_path)
        enrichment = get_llm_provider("enrichment", tmp_path)
        report = get_llm_provider("report", tmp_path)

        assert isinstance(chat, ClaudeAdapter)
        assert isinstance(enrichment, OllamaAdapter)
        assert isinstance(report, LlamaCppAdapter)

    def test_base_url_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "chat_inference": {
                    "provider": "ollama",
                    "base_url": "http://10.0.0.5:9999",
                }
            },
        )
        provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._base_url == "http://10.0.0.5:9999"
