"""Unit tests for DockerProbe."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from domain.runtime.models import RuntimeDependencyStatus
from infrastructure.runtime.docker_probe import DockerProbe


def _make_proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = ""
    proc.returncode = returncode
    return proc


class TestDockerProbeNotOnPath:
    def test_not_on_path_returns_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            status = DockerProbe().probe()
        assert status.installed is False
        assert status.binary_path is None
        assert status.version is None
        assert status.error == "docker not on PATH"


class TestDockerProbeVersionInvocation:
    def _probe_with(self, stdout: str, returncode: int = 0) -> RuntimeDependencyStatus:
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch(
                "subprocess.run",
                return_value=_make_proc(stdout, returncode),
            ),
        ):
            return DockerProbe().probe()

    def test_success_parses_semver(self) -> None:
        status = self._probe_with("Docker version 27.5.1, build 9f9e405")
        assert status.installed is True
        assert status.version == "27.5.1"
        assert status.error is None
        assert status.binary_path == "/usr/bin/docker"

    def test_success_strips_ansi(self) -> None:
        status = self._probe_with("\x1b[32mDocker version 24.0.7\x1b[0m")
        assert status.installed is True
        assert status.version == "24.0.7"

    def test_nonzero_exit_returns_not_installed(self) -> None:
        status = self._probe_with("error", returncode=1)
        assert status.installed is False
        assert "exit 1" in (status.error or "")

    def test_empty_output_returns_not_installed(self) -> None:
        status = self._probe_with("")
        assert status.installed is False
        assert "empty output" in (status.error or "")

    def test_no_semver_installed_without_version(self) -> None:
        status = self._probe_with("Docker dev build")
        assert status.installed is True
        assert status.version is None

    def test_timeout_returns_not_installed(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("docker", 10),
            ),
        ):
            status = DockerProbe().probe()
        assert status.installed is False
        assert "timed out" in (status.error or "")

    def test_unexpected_exception_returns_not_installed(
        self,
    ) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch(
                "subprocess.run",
                side_effect=OSError("permission denied"),
            ),
        ):
            status = DockerProbe().probe()
        assert status.installed is False
        assert "permission denied" in (status.error or "")
