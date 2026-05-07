"""Builds runtime probes from config."""

from __future__ import annotations

from pathlib import Path

from application.triage.factory import load_triage_provider
from domain.runtime.probe import RuntimeDependencyProbe
from infrastructure.runtime.claude_probe import ClaudeCodeProbe
from infrastructure.runtime.opencode_probe import OpenCodeProbe


def build_runtime_dependency_probes(
    *, base_path: str | Path
) -> list[RuntimeDependencyProbe]:
    """Registers probes for configured runtimes."""
    try:
        provider = load_triage_provider(app_root=Path(base_path))
    except (FileNotFoundError, PermissionError):
        provider = ""

    probes: list[RuntimeDependencyProbe] = []
    if provider == "claude_code":
        probes.append(ClaudeCodeProbe())
    if provider == "open_code":
        probes.append(OpenCodeProbe())
    return probes
