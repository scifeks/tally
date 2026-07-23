"""Unit tests for get_llm_provider raising on unknown providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.llm.factory import get_llm_provider

_OLLAMA_URL = "http://localhost:11434"


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "ollama": {
            "base_url": _OLLAMA_URL,
            "model": "qwen3:14b",
        },
        "chat_inference": {"provider": "ollama"},
        "enrichment_inference": {"provider": "ollama"},
        "report_inference": {"provider": "ollama"},
        "embedding_inference": {
            "provider": "ollama",
            "model": "nomic-embed-text:latest",
        },
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestGetLlmProviderRaisesOnUnknown:
    def test_unknown_chat_provider(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {"chat_inference": {"provider": "anthropic"}},
        )
        with pytest.raises(ValueError, match="anthropic"):
            get_llm_provider("chat", tmp_path)

    def test_unknown_enrichment_provider(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {"enrichment_inference": {"provider": "deepseek"}},
        )
        with pytest.raises(ValueError, match="deepseek"):
            get_llm_provider("enrichment", tmp_path)
