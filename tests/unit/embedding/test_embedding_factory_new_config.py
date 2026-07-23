"""Unit tests for get_embedding_provider with new config."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.embedding.factory import (
    get_embedding_provider,
)
from infrastructure.embedding.llama_cpp_embedding_adapter import (
    LlamaCppEmbeddingAdapter,
)
from infrastructure.embedding.ollama_embedding_adapter import (
    OllamaEmbeddingAdapter,
)
from infrastructure.embedding.voyage_embedding_adapter import (
    VoyageEmbeddingAdapter,
)


def _write_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "qwen3:14b",
        },
        "llama_cpp": {
            "base_url": "http://localhost:8000",
            "model": "llama2",
        },
        "voyage": {
            "api_key": "pa-test",
            "model": "voyage-3",
        },
        "embedding_inference": {
            "provider": "ollama",
            "model": "nomic-embed-text:latest",
        },
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestEmbeddingFactoryNewConfig:
    def test_returns_ollama(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, OllamaEmbeddingAdapter)

    def test_returns_llama_cpp(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {"embedding_inference": {"provider": "llama_cpp"}},
        )
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, LlamaCppEmbeddingAdapter)

    def test_returns_voyage(self, tmp_path: Path) -> None:
        with patch("infrastructure.embedding.voyage_embedding_adapter.VoyageClient"):
            _write_config(
                tmp_path,
                {"embedding_inference": {"provider": "voyage"}},
            )
            provider = get_embedding_provider(tmp_path)
            assert isinstance(provider, VoyageEmbeddingAdapter)

    def test_model_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "embedding_inference": {
                    "provider": "ollama",
                    "model": "all-MiniLM-L6-v2:latest",
                }
            },
        )
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, OllamaEmbeddingAdapter)
        assert provider._model == "all-MiniLM-L6-v2:latest"

    def test_timeout_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "embedding_inference": {
                    "provider": "ollama",
                    "timeout_seconds": 120,
                }
            },
        )
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, OllamaEmbeddingAdapter)
        assert provider._timeout == 120

    def test_missing_feature_raises(self, tmp_path: Path) -> None:
        _write_config(tmp_path, {"embedding_inference": None})
        with pytest.raises(ValueError, match="embedding_inference"):
            get_embedding_provider(tmp_path)

    def test_missing_provider_raises(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {"embedding_inference": {"provider": "nonexistent"}},
        )
        with pytest.raises(ValueError, match="nonexistent"):
            get_embedding_provider(tmp_path)

    def test_all_overrides(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "embedding_inference": {
                    "provider": "llama_cpp",
                    "model": "custom-embed",
                    "timeout_seconds": 200,
                }
            },
        )
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, LlamaCppEmbeddingAdapter)
        assert provider._model == "custom-embed"
        assert provider._timeout == 200

    def test_base_url_override(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            {
                "embedding_inference": {
                    "provider": "ollama",
                    "base_url": "http://10.1.20.101:11436",
                    "model": "nomic-embed-text:latest",
                }
            },
        )
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, OllamaEmbeddingAdapter)
        assert provider._base_url == "http://10.1.20.101:11436"
