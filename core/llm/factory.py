"""Factory for instantiating LLMProvider adapters from global config."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from core.config.manager import ConfigManager

from .base import LLMProvider
from .claude_adapter import ClaudeAdapter
from .ollama_adapter import OllamaAdapter

Role = Literal["chat", "enrichment", "report"]


def get_llm_provider(role: Role, base_path: str | Path) -> LLMProvider:
    """Instantiate the LLMProvider configured for the given role.

    Reads the appropriate *_llm_provider key from global.json and returns
    the matching adapter.

    Raises:
        ValueError: For unknown provider names.
    """
    config = ConfigManager(str(base_path)).global_config
    provider_name: str = {
        "chat": config.chat_llm_provider,
        "enrichment": config.enrichment_llm_provider,
        "report": config.report_llm_provider,
    }[role]

    if provider_name == "ollama":
        assert config.ollama is not None
        return OllamaAdapter(
            base_url=config.ollama.base_url,
            model=config.ollama.model,
            timeout_seconds=config.ollama.timeout_seconds,
        )
    if provider_name == "claude":
        assert config.claude is not None
        return ClaudeAdapter(
            api_key=config.claude.api_key,
            model=config.claude.model,
            max_tokens=config.claude.max_tokens,
            timeout_seconds=config.claude.timeout_seconds,
        )
    raise ValueError(
        f"Unknown llm_provider {provider_name!r} for role {role!r}. "
        "Registered providers: ollama, claude"
    )
