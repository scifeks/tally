"""Factory for instantiating LLMProvider adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from application.ports.llm_provider import LLMProvider
from core.config.manager import ConfigManager

from .claude_adapter import ClaudeAdapter
from .llama_cpp_adapter import LlamaCppAdapter
from .ollama_adapter import OllamaAdapter

Role = Literal["chat", "enrichment", "report"]

_FEATURE_FIELDS: dict[Role, str] = {
    "chat": "chat_inference",
    "enrichment": "enrichment_inference",
    "report": "report_inference",
}


def get_llm_provider(role: Role, base_path: str | Path) -> LLMProvider:
    config = ConfigManager(str(base_path)).global_config
    feature_field = _FEATURE_FIELDS[role]
    feature = getattr(config, feature_field, None)
    if feature is None:
        raise ValueError(f"{feature_field!r} not configured in global.json")

    provider_name = feature.provider
    provider_config = getattr(config, provider_name, None)
    if provider_config is None:
        raise ValueError(f"Provider {provider_name!r} not configured in global.json")

    merged = provider_config.model_dump()
    for key in (
        "base_url",
        "model",
        "timeout_seconds",
        "num_ctx",
        "max_tokens",
    ):
        val = getattr(feature, key, None)
        if val is not None:
            merged[key] = val

    if provider_name == "ollama":
        return OllamaAdapter(
            base_url=merged["base_url"],
            model=merged["model"],
            timeout_seconds=merged.get("timeout_seconds", 60),
            num_ctx=merged.get("num_ctx"),
        )
    if provider_name == "llama_cpp":
        return LlamaCppAdapter(
            base_url=merged["base_url"],
            model=merged["model"],
            timeout_seconds=merged.get("timeout_seconds", 60),
            num_ctx=merged.get("num_ctx"),
        )
    if provider_name == "claude":
        return ClaudeAdapter(
            api_key=merged["api_key"],
            model=merged["model"],
            max_tokens=merged.get("max_tokens", 1024),
            timeout_seconds=merged.get("timeout_seconds", 60),
        )
    raise ValueError(
        f"Unknown provider {provider_name!r} for "
        f"role {role!r}. "
        "Registered providers: ollama, llama_cpp, claude"
    )
