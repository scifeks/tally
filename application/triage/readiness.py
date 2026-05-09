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
) -> TriageReadiness:
    """Resolves whether triage is structurally available.

    Checks provider config and Docker availability. Does not check
    image existence; that is a runtime concern handled on first use.
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

    return TriageReadiness(
        provider=provider,
        backend_label=backend_label,
        enabled=True,
        reason=None,
    )
