"""Builds runtime probes from config."""

from __future__ import annotations

from pathlib import Path

from domain.runtime.probe import RuntimeDependencyProbe
from factories.scanning import create_docker_probe


def build_runtime_dependency_probes(
    *,
    base_path: str | Path,
) -> list[RuntimeDependencyProbe]:
    """Registers probes for configured runtimes."""
    _ = base_path
    return [create_docker_probe()]
