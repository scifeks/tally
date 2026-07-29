"""Resolve Antares inference configuration from GlobalConfig."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config.schemas.feature_inference_config import (
        FeatureInferenceConfig,
    )
    from core.config.schemas.global_config import GlobalConfig


@dataclass(frozen=True)
class AntaresResolvedConfig:
    """Resolved Antares inference configuration."""

    endpoint_url: str
    model: str
    needs_shim: bool
    ollama_base_url: str | None
    timeout_seconds: int
    max_cwes: int | None
    workers: int | None


def resolve_antares_config(config: GlobalConfig) -> AntaresResolvedConfig:
    """Resolve Antares inference config with model fallback chain."""
    if config.antares_inference is None:
        raise ValueError("antares_inference not configured in global.json")

    antares = config.antares_inference
    provider_name = antares.provider

    model = _resolve_model(config, antares)
    endpoint_url, ollama_base_url = _resolve_endpoint(config, antares, provider_name)
    timeout_seconds = antares.timeout_seconds or 300
    needs_shim = provider_name == "ollama"

    sweep_config = config.antares_sweep_config or {}
    max_cwes = sweep_config.get("max_cwes")
    workers = sweep_config.get("workers")

    return AntaresResolvedConfig(
        endpoint_url=endpoint_url,
        model=model,
        needs_shim=needs_shim,
        ollama_base_url=ollama_base_url,
        timeout_seconds=timeout_seconds,
        max_cwes=max_cwes,
        workers=workers,
    )


def _resolve_model(
    config: GlobalConfig,
    antares_inference: FeatureInferenceConfig,
) -> str:
    """Resolve model with fallback chain.

    Ollama: falls back through chat/triage Ollama models.
    Other providers: checks only that provider's own config.
    """
    if antares_inference.model:
        return antares_inference.model

    provider_name = antares_inference.provider

    if provider_name == "ollama":
        if config.chat_inference and config.chat_inference.provider == "ollama":
            if config.chat_inference.model:
                return config.chat_inference.model
            if config.ollama and config.ollama.model:
                return config.ollama.model

        if config.triage_inference and config.triage_inference.provider == "ollama":
            if config.triage_inference.model:
                return config.triage_inference.model
            if config.ollama and config.ollama.model:
                return config.ollama.model

        if config.ollama and config.ollama.model:
            return config.ollama.model

    provider_config = getattr(config, provider_name, None)
    if provider_config and hasattr(provider_config, "model"):
        provider_model = getattr(provider_config, "model", None)
        if provider_model:
            return provider_model

    raise ValueError(
        f"Could not resolve model for provider {provider_name!r}: "
        f"no explicit model in antares_inference, and no default model "
        f"in {provider_name} config"
    )


def _resolve_endpoint(
    config: GlobalConfig,
    antares_inference: FeatureInferenceConfig,
    provider_name: str,
) -> tuple[str, str | None]:
    """Resolve endpoint URL and ollama_base_url."""
    if provider_name == "ollama":
        if config.ollama and config.ollama.base_url:
            return (config.ollama.base_url, config.ollama.base_url)
        raise ValueError("Ollama provider selected but ollama.base_url not configured")

    if provider_name == "llama_cpp":
        base_url = antares_inference.base_url or (
            config.llama_cpp.base_url if config.llama_cpp else None
        )
        if not base_url:
            raise ValueError(
                "llama_cpp provider selected but base_url not configured "
                "in antares_inference or llama_cpp"
            )
        return (base_url, None)

    if antares_inference.base_url:
        return (antares_inference.base_url, None)

    raise ValueError(
        f"Provider {provider_name!r} requires base_url in antares_inference"
    )
