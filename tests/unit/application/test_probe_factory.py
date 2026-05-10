"""Tests runtime probe selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from application.runtime import build_runtime_dependency_probes
from infrastructure.runtime.docker_probe import DockerProbe


class TestBuildRuntimeDependencyProbes:
    def test_returns_docker_probe(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            probes = build_runtime_dependency_probes(base_path=tmp_path)
        assert len(probes) == 1
        assert isinstance(probes[0], DockerProbe)

    def test_docker_probe_present_regardless_of_provider(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            probes = build_runtime_dependency_probes(base_path=tmp_path)
        names = [p.requirement.name for p in probes]
        assert "docker" in names
