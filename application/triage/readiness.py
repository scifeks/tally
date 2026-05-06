"""Triage readiness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from application.runtime.dependency_service import RuntimeDependencyService

from .factory import load_triage_provider

_TRIAGE_BACKEND_LABELS = {
    "claude_code": "Claude Code",
    "open_code": "OpenCode",
}

_TRIAGE_RUNTIME_NAMES = {
    "claude_code": "claude",
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
    runtime_service: RuntimeDependencyService | None,
) -> TriageReadiness:
    """Resolves whether triage can run."""
    try:
        provider = load_triage_provider(app_root=Path(base_path))
    except FileNotFoundError:
        provider = ""

    backend_label = triage_backend_label(provider)

    if provider == "":
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason="Triage disabled in config",
        )

    if provider == "open_code":
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=False,
            reason="OpenCode backend not implemented yet",
        )

    runtime_name = _TRIAGE_RUNTIME_NAMES.get(provider)
    if runtime_name is None or runtime_service is None:
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=True,
            reason=None,
        )

    if runtime_service.is_installed(runtime_name):
        return TriageReadiness(
            provider=provider,
            backend_label=backend_label,
            enabled=True,
            reason=None,
        )

    label = backend_label or provider
    return TriageReadiness(
        provider=provider,
        backend_label=backend_label,
        enabled=False,
        reason=f"{label} required for Triage",
    )
