"""Unit tests for infrastructure.tools.wrappers.utils.pip_deps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from infrastructure.tools.wrappers.utils.pip_deps import (
    find_or_generate_requirements,
    reset_attempted,
)


def _mock_proc(returncode: int = 0, stdout: str = "package==1.0\n"):
    return type(
        "R",
        (),
        {"returncode": returncode, "stdout": stdout, "stderr": ""},
    )()


class TestFindOrGenerateRequirementsLocal:
    def setup_method(self) -> None:
        reset_attempted()

    def test_returns_requirements_txt_when_present(self, tmp_path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.28.0\n")
        result = find_or_generate_requirements(str(tmp_path))
        assert result == str(req)

    def test_returns_none_when_no_dep_files(self, tmp_path) -> None:
        result = find_or_generate_requirements(str(tmp_path))
        assert result is None

    def test_poetry_lock_triggers_poetry_export(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, "requests==2.28.0\n"),
        ) as mock_run:
            result = find_or_generate_requirements(str(tmp_path))

        assert result is not None
        assert result.endswith(".tally_requirements.txt")
        cmd = mock_run.call_args[0][0]
        assert "poetry" in cmd
        assert "export" in cmd

    def test_poetry_export_writes_output_file(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, "requests==2.28.0\n"),
        ):
            result = find_or_generate_requirements(str(tmp_path))

        assert result is not None
        written = Path(result)
        assert written.exists()
        assert written.read_text() == "requests==2.28.0\n"

    def test_pipfile_lock_triggers_pipenv(self, tmp_path) -> None:
        (tmp_path / "Pipfile.lock").write_text("{}")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, "requests==2.28.0\n"),
        ) as mock_run:
            result = find_or_generate_requirements(str(tmp_path))

        assert result is not None
        cmd = mock_run.call_args[0][0]
        assert "pipenv" in cmd

    def test_pyproject_toml_triggers_pip_freeze(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, "requests==2.28.0\n"),
        ) as mock_run:
            result = find_or_generate_requirements(str(tmp_path))

        assert result is not None
        cmd = mock_run.call_args[0][0]
        assert "pip" in cmd
        assert "freeze" in cmd
        assert "--path" not in cmd

    def test_setup_py_triggers_pip_freeze(self, tmp_path) -> None:
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, "requests==2.28.0\n"),
        ) as mock_run:
            result = find_or_generate_requirements(str(tmp_path))

        assert result is not None
        cmd = mock_run.call_args[0][0]
        assert "freeze" in cmd

    def test_setup_cfg_triggers_pip_freeze(self, tmp_path) -> None:
        (tmp_path / "setup.cfg").write_text("[metadata]\n")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, "requests==2.28.0\n"),
        ) as mock_run:
            result = find_or_generate_requirements(str(tmp_path))

        assert result is not None
        cmd = mock_run.call_args[0][0]
        assert "freeze" in cmd

    def test_returns_none_when_export_fails(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(returncode=1, stdout=""),
        ):
            result = find_or_generate_requirements(str(tmp_path))
        assert result is None

    def test_returns_none_when_export_produces_no_output(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(0, stdout=""),
        ):
            result = find_or_generate_requirements(str(tmp_path))
        assert result is None

    def test_no_retry_after_failed_attempt(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(1, stdout=""),
        ) as mock_run:
            find_or_generate_requirements(str(tmp_path))
            result = find_or_generate_requirements(str(tmp_path))

        assert result is None
        mock_run.assert_called_once()

    def test_reset_attempted_allows_retry(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=_mock_proc(1, stdout=""),
        ) as mock_run:
            find_or_generate_requirements(str(tmp_path))
            reset_attempted()
            find_or_generate_requirements(str(tmp_path))

        assert mock_run.call_count == 2

    def test_requirements_txt_bypasses_dedup_set(self, tmp_path) -> None:
        """requirements.txt detection bypasses the dedup set — always returned."""
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.28.0\n")
        result1 = find_or_generate_requirements(str(tmp_path))
        result2 = find_or_generate_requirements(str(tmp_path))
        assert result1 == result2 == str(req)

    def test_export_runs_with_cwd(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        captured_kwargs: dict = {}

        def _capture(cmd, **kwargs):
            captured_kwargs.update(kwargs)
            return _mock_proc(0, "requests==2.28.0\n")

        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            side_effect=_capture,
        ):
            find_or_generate_requirements(str(tmp_path))

        assert captured_kwargs.get("cwd") == str(tmp_path)


class TestFindOrGenerateRequirementsDocker:
    def setup_method(self) -> None:
        reset_attempted()

    def test_returns_requirements_txt_path_when_exists_in_container(self) -> None:
        """When requirements.txt exists in the container, return its path directly
        without running any export command (no subprocess call needed)."""

        def _mock(cmd, **_kwargs):
            # docker exec test -f /app/requirements.txt → found
            return type("R", (), {"returncode": 0})()

        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            side_effect=_mock,
        ):
            result = find_or_generate_requirements(
                "/app", container_name="my-container"
            )

        assert result == "/app/requirements.txt"

    def test_docker_file_check_uses_docker_test_command(self) -> None:
        """File existence checks use docker exec <container> test -f <path>."""
        calls: list = []

        def _mock(cmd, **_kwargs):
            calls.append(cmd)
            return type("R", (), {"returncode": 0})()

        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            side_effect=_mock,
        ):
            find_or_generate_requirements("/app", container_name="my-container")

        assert calls, "at least one subprocess call expected"
        check_cmd = calls[0]
        assert check_cmd[0] == "docker"
        assert "exec" in check_cmd
        assert "test" in check_cmd
        assert "my-container" in check_cmd
        assert "/app/requirements.txt" in check_cmd

    def test_returns_none_when_no_files_found_in_container(self) -> None:
        """Returns None when no dependency files exist in the container."""

        def _mock(cmd, **_kwargs):
            # All test -f checks return not found
            return type("R", (), {"returncode": 1})()

        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            side_effect=_mock,
        ):
            result = find_or_generate_requirements(
                "/app", container_name="my-container"
            )

        assert result is None
