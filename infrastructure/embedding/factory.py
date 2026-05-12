"""Factory for instantiating EmbeddingProvider adapters."""

from __future__ import annotations

import logging
from pathlib import Path

from application.ports.embedding_provider import (
    EmbeddingProvider,
)
from core.config.manager import ConfigManager

from .llama_cpp_embedding_adapter import (
    LlamaCppEmbeddingAdapter,
)
from .ollama_embedding_adapter import OllamaEmbeddingAdapter

logger = logging.getLogger(__name__)


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

    debug = feature.debug

    if provider_name == "llama_cpp" and feature.base_url is None:
        logger.warning(
            "embedding_inference uses llama_cpp without a base_url "
            "override. llama.cpp servers are single-model; the model "
            "parameter is ignored. Set base_url to the server running "
            "your embedding model."
        )

    if provider_name == "ollama":
        return OllamaEmbeddingAdapter(
            base_url=merged["base_url"],
            model=merged["model"],
            timeout_seconds=merged.get("timeout_seconds", 60),
            debug=debug,
        )
    if provider_name == "llama_cpp":
        return LlamaCppEmbeddingAdapter(
            base_url=merged["base_url"],
            model=merged["model"],
            timeout_seconds=merged.get("timeout_seconds", 60),
            debug=debug,
        )
    raise ValueError(
        f"Unknown embedding provider {provider_name!r}. "
        "Registered providers: ollama, llama_cpp"
    )
