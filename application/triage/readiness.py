"""Triage readiness helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

_TRIAGE_BACKEND_LABELS = {
    "claude": "Claude Code",
    "ollama": "OpenCode (Ollama)",
    "llama_cpp": "OpenCode (llama.cpp)",
    "claude_code": "Claude Code",
    "open_code": "OpenCode",
    "opencode": "OpenCode",
    "openai": "OpenAI",
}

_FRONTIER_PROVIDERS: frozenset[str] = frozenset({"claude", "claude_code", "openai"})


@dataclass(frozen=True)
class TriageReadiness:
    provider: str
    backend_label: str | None
    enabled: bool
    reason: str | None
    triage_mode: str | None = None


def triage_backend_label(provider: str) -> str | None:
    return _TRIAGE_BACKEND_LABELS.get(provider)


def compute_triage_readiness(
    provider: str,
    docker_available: bool,
    api_key: str = "",
) -> TriageReadiness:
    """Check whether triage is structurally available.

    Frontier providers (Claude, OpenAI) run in auto mode when an API key
    is configured, which requires Docker. Without a key they fall back
    to MCP mode, which needs no container. Local providers always run
    in auto mode and require Docker.
    """
    backend_label = triage_backend_label(provider)

    if provider == "":
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason="Triage disabled in config",
            triage_mode=None,
        )

    if provider in _FRONTIER_PROVIDERS:
        if _has_api_key(api_key, provider):
            if not docker_available:
                return TriageReadiness(
                    provider=provider,
                    backend_label=backend_label,
                    enabled=False,
                    reason="Docker is not installed or not running",
                    triage_mode="auto",
                )
            return TriageReadiness(
                provider=provider,
                backend_label=backend_label,
                enabled=True,
                reason=None,
                triage_mode="auto",
            )
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=True,
            reason=None,
            triage_mode="mcp",
        )

    # Local providers: auto mode, Docker required.
    if not docker_available:
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason="Docker is not installed or not running",
            triage_mode="auto",
        )
    return TriageReadiness(
        provider=provider,
        backend_label=backend_label,
        enabled=True,
        reason=None,
        triage_mode="auto",
    )


def _has_api_key(key: str, provider: str) -> bool:
    """Check whether an API key is available from config or env."""
    if key:
        return True
    env_map = {
        "claude": "ANTHROPIC_API_KEY",
        "claude_code": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var:
        return bool(os.environ.get(env_var))
    return False
