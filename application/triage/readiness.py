"""Triage readiness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .factory import load_triage_provider

_TRIAGE_BACKEND_LABELS = {
    "claude": "Claude Code",
    "ollama": "OpenCode (Ollama)",
    "llama_cpp": "OpenCode (llama.cpp)",
    "claude_code": "Claude Code",
    "open_code": "OpenCode",
}


@dataclass(frozen=True)
class TriageReadiness:
    provider: str
    backend_label: str | None
    enabled: bool
    reason: str | None


def triage_backend_label(provider: str) -> str | None:
    return _TRIAGE_BACKEND_LABELS.get(provider)


def compute_triage_readiness(
    *,
    base_path: str | Path,
    docker_available: bool,
    claude_api_key: str = "",
) -> TriageReadiness:
    """Check whether triage is structurally available.

    Verifies provider config and Docker availability. Image existence
    is deferred to runtime since containers may not be pre-pulled.
    """
    try:
        provider = load_triage_provider(app_root=Path(base_path))
    except (FileNotFoundError, PermissionError):
        provider = ""

    backend_label = triage_backend_label(provider)

    if provider == "":
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason="Triage disabled in config",
        )

    if not docker_available:
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason="Docker is not installed or not running",
        )

    if provider == "claude_code" and not _has_anthropic_key(claude_api_key):
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason=(
                "No Anthropic API key configured. Set"
                " claude.api_key in config/global.json or"
                " export ANTHROPIC_API_KEY. For interactive"
                " triage without an API key, use MCP triage"
                " mode."
            ),
        )

    return TriageReadiness(
        provider=provider,
        backend_label=backend_label,
        enabled=True,
        reason=None,
    )


def _has_anthropic_key(config_key: str) -> bool:
    """Check if Anthropic API key is available from config or env."""
    import os

    if config_key:
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
