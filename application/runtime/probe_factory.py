"""Builds runtime probes from config."""

from __future__ import annotations

from pathlib import Path

from domain.runtime.probe import RuntimeDependencyProbe
from infrastructure.runtime.docker_probe import DockerProbe


def build_runtime_dependency_probes(
    *,
    base_path: str | Path,  # kept for caller compatibility
) -> list[RuntimeDependencyProbe]:
    """Registers probes for configured runtimes."""
    _ = base_path
    return [DockerProbe()]
