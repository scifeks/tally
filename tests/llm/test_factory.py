"""Unit tests for get_llm_provider factory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.llm.factory import get_llm_provider
from core.llm.ollama_adapter import OllamaAdapter

_OLLAMA_URL = "http://localhost:11434"


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "chat_llm_provider": "ollama",
        "enrichment_llm_provider": "ollama",
        "report_llm_provider": "ollama",
        "ollama": {
            "base_url": _OLLAMA_URL,
            "model": "qwen3:14b",
            "embedding_model": "nomic-embed-text:latest",
        },
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestGetLlmProviderReturnsOllama:
    def test_chat_role(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_enrichment_role(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("enrichment", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_report_role(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, OllamaAdapter)


class TestGetLlmProviderRaisesOnUnknown:
    def test_unknown_chat_provider(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"chat_llm_provider": "anthropic"})
        with pytest.raises(ValueError, match="anthropic"):
            get_llm_provider("chat", tmp_path)

    def test_unknown_enrichment_provider(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"enrichment_llm_provider": "openai"})
        with pytest.raises(ValueError, match="openai"):
            get_llm_provider("enrichment", tmp_path)


class TestRolesResolveIndependently:
    def test_chat_unknown_enrichment_ok(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"chat_llm_provider": "unknown"})
        with pytest.raises(ValueError):
            get_llm_provider("chat", tmp_path)
        provider = get_llm_provider("enrichment", tmp_path)
        assert isinstance(provider, OllamaAdapter)
