"""Unit tests for infrastructure.tools.wrappers.utils.install_fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.tools.wrappers.utils.install_fallback import (
    ensure_lockfile,
    reset_attempted,
)


def _mock_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestEnsureLockfileLocal:
    def setup_method(self) -> None:
        reset_attempted()

    def test_returns_true_when_lockfile_already_exists(self, tmp_path) -> None:
        (tmp_path / "package-lock.json").write_text("{}")
        result = ensure_lockfile(
            "npm-audit",
            str(tmp_path),
            "package-lock.json",
            ["npm", "install", "--package-lock-only"],
        )
        assert result is True

    def test_attempts_install_when_lockfile_missing(self, tmp_path) -> None:
        def _create_lockfile(cmd, **kwargs):
            (tmp_path / "package-lock.json").write_text("{}")
            return _mock_proc(0)

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_create_lockfile,
        ) as mock_run:
            result = ensure_lockfile(
                "npm-audit",
                str(tmp_path),
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
            )

        assert result is True
        mock_run.assert_called_once()

    def test_returns_false_when_install_fails(self, tmp_path) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=_mock_proc(returncode=1),
        ):
            result = ensure_lockfile(
                "npm-audit",
                str(tmp_path),
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
            )
        assert result is False

    def test_returns_false_when_install_succeeds_but_file_still_missing(
        self, tmp_path
    ) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=_mock_proc(0),
        ):
            result = ensure_lockfile(
                "npm-audit",
                str(tmp_path),
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
            )
        assert result is False

    def test_returns_false_when_install_raises(self, tmp_path) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=OSError("npm not found"),
        ):
            result = ensure_lockfile(
                "npm-audit",
                str(tmp_path),
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
            )
        assert result is False

    def test_no_retry_for_same_tool_and_path(self, tmp_path) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=_mock_proc(1),
        ) as mock_run:
            ensure_lockfile("npm-audit", str(tmp_path), "package-lock.json", ["npm"])
            result = ensure_lockfile(
                "npm-audit", str(tmp_path), "package-lock.json", ["npm"]
            )

        assert result is False
        mock_run.assert_called_once()

    def test_different_tool_same_path_is_retried(self, tmp_path) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=_mock_proc(1),
        ) as mock_run:
            ensure_lockfile("npm-audit", str(tmp_path), "package-lock.json", ["npm"])
            ensure_lockfile(
                "composer-audit", str(tmp_path), "composer.lock", ["composer"]
            )

        assert mock_run.call_count == 2

    def test_reset_attempted_clears_dedup(self, tmp_path) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=_mock_proc(1),
        ) as mock_run:
            ensure_lockfile("npm-audit", str(tmp_path), "package-lock.json", ["npm"])
            reset_attempted()
            ensure_lockfile("npm-audit", str(tmp_path), "package-lock.json", ["npm"])

        assert mock_run.call_count == 2

    def test_install_runs_with_correct_cwd(self, tmp_path) -> None:
        calls = []

        def _capture(cmd, **kwargs):
            calls.append(kwargs.get("cwd"))
            (tmp_path / "package-lock.json").write_text("{}")
            return _mock_proc(0)

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_capture,
        ):
            ensure_lockfile(
                "npm-audit",
                str(tmp_path),
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
            )

        assert calls[0] == str(tmp_path)


class TestEnsureLockfileDocker:
    def setup_method(self) -> None:
        reset_attempted()

    def _make_docker_checker(self, file_exists: bool, install_rc: int = 0):
        """Return subprocess.run mock that handles test -f and install commands."""
        call_count = {"n": 0}

        def _mock(cmd, **kwargs):
            if "test" in cmd:
                # Simulate docker exec test -f
                rc = 0 if file_exists else 1
                return type("R", (), {"returncode": rc, "stdout": "", "stderr": ""})()
            # install command
            call_count["n"] += 1
            return _mock_proc(install_rc)

        return _mock

    def test_returns_true_when_docker_file_exists(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=self._make_docker_checker(file_exists=True),
        ):
            result = ensure_lockfile(
                "npm-audit",
                "/app",
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
                container_name="my-container",
            )
        assert result is True

    def test_attempts_docker_install_when_file_missing(self) -> None:
        install_calls = []

        def _mock(cmd, **kwargs):
            if "test" in cmd:
                # First call: file missing; subsequent calls (after install): exists
                return type(
                    "R",
                    (),
                    {
                        "returncode": 1 if len(install_calls) == 0 else 0,
                        "stdout": "",
                        "stderr": "",
                    },
                )()
            install_calls.append(cmd)
            return _mock_proc(0)

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            ensure_lockfile(
                "npm-audit",
                "/app",
                "package-lock.json",
                ["npm", "install", "--package-lock-only"],
                container_name="my-container",
            )

        assert len(install_calls) == 1
        # docker exec -w <path> <container> <cmd>
        assert install_calls[0][0] == "docker"
        assert "-w" in install_calls[0]
        assert "my-container" in install_calls[0]

    def test_docker_install_command_includes_workdir(self) -> None:
        install_calls = []

        def _mock(cmd, **kwargs):
            if "test" in cmd:
                return type(
                    "R",
                    (),
                    {
                        "returncode": 1 if not install_calls else 0,
                        "stdout": "",
                        "stderr": "",
                    },
                )()
            install_calls.append(cmd)
            return _mock_proc(0)

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            ensure_lockfile(
                "npm-audit",
                "/app/myrepo",
                "package-lock.json",
                ["npm", "install"],
                container_name="testcontainer",
            )

        assert install_calls, "install command should have been called"
        cmd = install_calls[0]
        w_idx = cmd.index("-w")
        assert cmd[w_idx + 1] == "/app/myrepo"
        assert "testcontainer" in cmd
