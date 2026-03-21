"""Unit tests for ClaudeAdapter factory integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.llm.claude_adapter import ClaudeAdapter
from core.llm.factory import get_llm_provider

_MODEL = "claude-opus-4-5"
_API_KEY = "test-key-abc"


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "chat_llm_provider": "claude",
        "enrichment_llm_provider": "ollama",
        "report_llm_provider": "ollama",
        "embedding_provider": "ollama_embedding",
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "qwen3:14b",
        },
        "ollama_embedding": {"model": "nomic-embed-text:latest"},
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
