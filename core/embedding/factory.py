"""Factory for instantiating EmbeddingProvider adapters from global config."""

from __future__ import annotations

from pathlib import Path

from core.config.manager import ConfigManager

from .base import EmbeddingProvider
from .ollama_embedding_adapter import OllamaEmbeddingAdapter


def get_embedding_provider(base_path: str | Path) -> EmbeddingProvider:
    """Instantiate the EmbeddingProvider configured in global.json.

    Raises:
        ValueError: For unknown provider names.
    """
    config = ConfigManager(str(base_path)).global_config
    provider_name = config.embedding_provider

    if provider_name == "ollama_embedding":
        assert config.ollama_embedding is not None
        return OllamaEmbeddingAdapter(
            base_url=config.ollama_embedding.base_url,
            model=config.ollama_embedding.model,
            timeout_seconds=config.ollama_embedding.timeout_seconds,
        )
    raise ValueError(
        f"Unknown embedding_provider {provider_name!r}. "
        "Registered providers: ollama_embedding"
    )
