"""Unit tests for OpenCodeProbe."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from domain.runtime.models import RuntimeDependencyStatus
from infrastructure.runtime.opencode_probe import OpenCodeProbe


def _make_proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = ""
    proc.returncode = returncode
    return proc


class TestOpenCodeProbeNotOnPath:
    def test_not_on_path_returns_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            status = OpenCodeProbe().probe()
        assert status.installed is False
        assert status.binary_path is None
        assert status.version is None
        assert status.error == "opencode not on PATH"


class TestOpenCodeProbeVersionInvocation:
    def _probe_with(self, stdout: str, returncode: int = 0) -> RuntimeDependencyStatus:
        with (
            patch("shutil.which", return_value="/usr/bin/opencode"),
            patch(
                "subprocess.run",
                return_value=_make_proc(stdout, returncode),
            ),
        ):
            return OpenCodeProbe().probe()

    def test_success_parses_semver(self) -> None:
        status = self._probe_with("OpenCode 1.2.3")
        assert status.installed is True
        assert status.version == "1.2.3"
        assert status.error is None
        assert status.binary_path == "/usr/bin/opencode"

    def test_success_strips_ansi(self) -> None:
        status = self._probe_with("\x1b[32mOpenCode 2.0.1\x1b[0m")
        assert status.installed is True
        assert status.version == "2.0.1"

    def test_nonzero_exit_returns_not_installed(self) -> None:
        status = self._probe_with("error", returncode=1)
        assert status.installed is False
        assert "exit 1" in (status.error or "")

    def test_empty_output_returns_not_installed(self) -> None:
        status = self._probe_with("")
        assert status.installed is False
        assert "empty output" in (status.error or "")

    def test_no_semver_in_output_installed_without_version(self) -> None:
        status = self._probe_with("OpenCode dev build")
        assert status.installed is True
        assert status.version is None

    def test_timeout_returns_not_installed(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/opencode"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("opencode", 10),
            ),
        ):
            status = OpenCodeProbe().probe()
        assert status.installed is False
        assert "timed out" in (status.error or "")

    def test_unexpected_exception_returns_not_installed(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/opencode"),
            patch(
                "subprocess.run",
                side_effect=OSError("permission denied"),
            ),
        ):
            status = OpenCodeProbe().probe()
        assert status.installed is False
        assert "permission denied" in (status.error or "")
