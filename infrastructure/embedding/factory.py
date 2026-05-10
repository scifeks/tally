"""Factory for instantiating EmbeddingProvider adapters."""

from __future__ import annotations

from pathlib import Path

from application.ports.embedding_provider import (
    EmbeddingProvider,
)
from core.config.manager import ConfigManager

from .llama_cpp_embedding_adapter import (
    LlamaCppEmbeddingAdapter,
)
from .ollama_embedding_adapter import OllamaEmbeddingAdapter


def get_embedding_provider(
    base_path: str | Path,
) -> EmbeddingProvider:
    config = ConfigManager(str(base_path)).global_config
    feature = config.embedding_inference
    if feature is None:
        raise ValueError("embedding_inference not configured in global.json")

    provider_name = feature.provider
    provider_config = getattr(config, provider_name, None)
    if provider_config is None:
        raise ValueError(f"Provider {provider_name!r} not configured in global.json")

    merged = provider_config.model_dump()
    for key in ("base_url", "model", "timeout_seconds"):
        val = getattr(feature, key, None)
        if val is not None:
            merged[key] = val

    if provider_name == "ollama":
        return OllamaEmbeddingAdapter(
            base_url=merged["base_url"],
            model=merged["model"],
            timeout_seconds=merged.get("timeout_seconds", 60),
        )
    if provider_name == "llama_cpp":
        return LlamaCppEmbeddingAdapter(
            base_url=merged["base_url"],
            model=merged["model"],
            timeout_seconds=merged.get("timeout_seconds", 60),
        )
    raise ValueError(
        f"Unknown embedding provider {provider_name!r}. "
        "Registered providers: ollama, llama_cpp"
    )
