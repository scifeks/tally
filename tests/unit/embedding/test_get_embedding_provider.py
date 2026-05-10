"""Unit tests for get_embedding_provider factory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.embedding.factory import get_embedding_provider
from infrastructure.embedding.ollama_embedding_adapter import OllamaEmbeddingAdapter

_URL = "http://localhost:11434"
_MODEL = "nomic-embed-text:latest"


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "ollama": {"base_url": _URL, "model": "qwen3:14b"},
        "embedding_inference": {
            "provider": "ollama",
            "model": _MODEL,
        },
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestFactory:
    def test_returns_ollama_embedding_adapter(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, OllamaEmbeddingAdapter)

    def test_raises_on_unknown_provider(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {"embedding_inference": {"provider": "unknown"}},
        )
        with pytest.raises(ValueError, match="unknown"):
            get_embedding_provider(tmp_path)
