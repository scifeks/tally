"""Unit tests for PipAuditDockerTool.build_execution_passes and build_command.

Regression tests for two bugs:
1. The base class set cwd to the container path (e.g. /app), which caused
   FileNotFoundError in subprocess because that path does not exist locally.
2. --path . was passed to pip-audit, causing "failed to list installed
   distributions" because --path adds to sys.path rather than selecting a
   project root, breaking pip-audit on environments like Python 3.7 containers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.config.schemas import Repository
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.docker.pip_audit import PipAuditDockerTool

_MODULE = "infrastructure.tools.wrappers.docker.pip_audit"


def _make_config():
    config = MagicMock()
    config.container.name = "dvpwa-sqli-1"
    config.container.tool_path = "/usr/local/bin/pip-audit"
    return config


def _make_repo(
    local_path: str, docker_path: str, dependencies_file: str = ""
) -> Repository:
    return Repository.model_construct(
        name="dvpa",
        type=["api"],
        path=local_path,
        docker_path=docker_path,
        container_name="dvpwa-sqli-1",
        languages=["python"],
        base_urls=[],
        test_dirs=[],
        ignore_dirs=[],
        dependencies_file=dependencies_file,
    )


def _make_context(repo: Repository, docker_path: str) -> ExecutionContext:
    registry = MagicMock()
    registry.get_repo_path.return_value = docker_path
    return ExecutionContext(
        project_name="DVPA",
        base_path="/tmp",
        repo=repo,
        tool_config=ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=True,
    )


class TestPipAuditDockerExecutionPasses:
    def test_cwd_is_none(self) -> None:
        """Docker tools must not set cwd — the container path is not a local path."""
        repo = _make_repo("/llm/code/repos/python/dvpwa", "/app")
        ctx = _make_context(repo, "/app")
        tool = PipAuditDockerTool(_make_config())
        # no deps_file → no container file check
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].cwd is None

    def test_repo_path_passed_as_kwarg(self) -> None:
        """The container docker_path is forwarded to build_command via kwargs."""
        docker_path = "/app"
        repo = _make_repo("/llm/code/repos/python/dvpwa", docker_path)
        ctx = _make_context(repo, docker_path)
        tool = PipAuditDockerTool(_make_config())
        passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["repo_path"] == docker_path

    def test_label_suffix_is_repo_name(self) -> None:
        repo = _make_repo("/llm/code/repos/python/dvpwa", "/app")
        ctx = _make_context(repo, "/app")
        tool = PipAuditDockerTool(_make_config())
        passes = tool.build_execution_passes(ctx)
        assert passes[0].label_suffix == "dvpa"

    def test_dependencies_file_kwarg_forwarded_when_file_exists_in_container(
        self,
    ) -> None:
        """When deps file exists in the container it is forwarded unchanged."""
        dep_file = "/app/requirements.txt"
        repo = _make_repo(
            "/llm/code/repos/python/dvpwa", "/app", dependencies_file=dep_file
        )
        ctx = _make_context(repo, "/app")
        tool = PipAuditDockerTool(_make_config())
        with patch(f"{_MODULE}._container_file_exists", return_value=True):
            passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["dependencies_file"] == dep_file

    def test_docker_always_produces_pass_without_dependencies_file(self) -> None:
        """Docker pip-audit must not skip even when no dependencies_file is set."""
        repo = _make_repo("/llm/code/repos/python/dvpwa", "/app")
        ctx = _make_context(repo, "/app")
        tool = PipAuditDockerTool(_make_config())
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].kwargs["dependencies_file"] == ""

    def test_missing_container_deps_file_resolves_and_copies(self, tmp_path) -> None:
        """When deps file is absent in container, _resolve_and_copy_deps is called.

        The helper delegates format detection to find_or_generate_requirements,
        so any lockfile flavour (requirements.txt, poetry.lock, Pipfile.lock,
        pyproject.toml, uv.lock, etc.) is handled without the wrapper
        hardcoding a filename.
        """
        local_repo = tmp_path / "myrepo"
        local_repo.mkdir()
        (local_repo / "poetry.lock").write_text("")

        dep_file = "/app/requirements.txt"
        repo = _make_repo(str(local_repo), "/app", dependencies_file=dep_file)
        ctx = _make_context(repo, "/app")
        tool = PipAuditDockerTool(_make_config())

        with (
            patch(f"{_MODULE}._container_file_exists", return_value=False),
            patch(
                f"{_MODULE}._resolve_and_copy_deps", return_value=dep_file
            ) as mock_resolve,
        ):
            passes = tool.build_execution_passes(ctx)

        mock_resolve.assert_called_once_with(str(local_repo), "dvpwa-sqli-1", dep_file)
        assert len(passes) == 1
        assert passes[0].kwargs["dependencies_file"] == dep_file

    def test_missing_container_deps_file_skips_when_no_local_lockfile(
        self,
    ) -> None:
        """When deps file absent in container and no local lockfile, skip the pass."""
        dep_file = "/app/requirements.txt"
        repo = _make_repo("", "/app", dependencies_file=dep_file)
        ctx = _make_context(repo, "/app")
        tool = PipAuditDockerTool(_make_config())

        with (
            patch(f"{_MODULE}._container_file_exists", return_value=False),
            patch(f"{_MODULE}._resolve_and_copy_deps", return_value=None),
        ):
            passes = tool.build_execution_passes(ctx)

        assert passes == []


class TestCheckAvailable:
    def test_returns_true_when_tool_exists_in_container(self) -> None:
        tool = PipAuditDockerTool(_make_config())
        with patch(f"{_MODULE}._container_file_exists", return_value=True):
            assert tool.check_available() is True

    def test_installs_and_returns_true_when_tool_missing(self) -> None:
        tool = PipAuditDockerTool(_make_config())
        with (
            patch(f"{_MODULE}._container_file_exists", return_value=False),
            patch(
                f"{_MODULE}._install_pip_audit_in_container", return_value=True
            ) as mock_install,
        ):
            result = tool.check_available()
        mock_install.assert_called_once_with("dvpwa-sqli-1")
        assert result is True

    def test_returns_false_when_install_fails(self) -> None:
        tool = PipAuditDockerTool(_make_config())
        with (
            patch(f"{_MODULE}._container_file_exists", return_value=False),
            patch(f"{_MODULE}._install_pip_audit_in_container", return_value=False),
        ):
            assert tool.check_available() is False


class TestResolveAndCopyDeps:
    def test_returns_none_when_no_local_repo_path(self) -> None:
        from infrastructure.tools.wrappers.docker.pip_audit import (
            _resolve_and_copy_deps,
        )

        with patch(f"{_MODULE}.find_or_generate_requirements", return_value=None):
            result = _resolve_and_copy_deps("", "my-container", "/app/req.txt")
        assert result is None

    def test_delegates_to_find_or_generate_requirements(self, tmp_path) -> None:
        from infrastructure.tools.wrappers.docker.pip_audit import (
            _resolve_and_copy_deps,
        )

        generated = str(tmp_path / ".tally_requirements.txt")
        with (
            patch(
                f"{_MODULE}.find_or_generate_requirements", return_value=generated
            ) as mock_find,
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = _resolve_and_copy_deps(
                str(tmp_path), "my-container", "/app/req.txt"
            )

        mock_find.assert_called_once_with(str(tmp_path))
        assert result == "/app/req.txt"

    def test_returns_none_when_docker_cp_fails(self, tmp_path) -> None:
        from infrastructure.tools.wrappers.docker.pip_audit import (
            _resolve_and_copy_deps,
        )

        generated = str(tmp_path / "requirements.txt")
        with (
            patch(f"{_MODULE}.find_or_generate_requirements", return_value=generated),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr=b"no such container")
            result = _resolve_and_copy_deps(
                str(tmp_path), "bad-container", "/app/req.txt"
            )
        assert result is None


class TestPipAuditDockerBuildCommand:
    def test_with_dependencies_file_includes_r_flag(self) -> None:
        """When dependencies_file is set, -r <path> must appear in the command."""
        tool = PipAuditDockerTool(_make_config())
        cmd = tool.build_command(
            repo_path="/app", dependencies_file="/app/requirements.txt"
        )
        assert "-r" in cmd
        r_idx = cmd.index("-r")
        assert cmd[r_idx + 1] == "/app/requirements.txt"

    def test_without_dependencies_file_excludes_r_flag(self) -> None:
        """When dependencies_file is absent, -r must not appear (full env scan)."""
        tool = PipAuditDockerTool(_make_config())
        cmd = tool.build_command(repo_path="/app", dependencies_file="")
        assert "-r" not in cmd

    def test_format_json(self) -> None:
        tool = PipAuditDockerTool(_make_config())
        cmd = tool.build_command(repo_path="/app")
        assert "--format" in cmd
        assert "json" in cmd

    def test_workdir_set_in_command(self) -> None:
        """docker exec must use -w <docker_path> so pip-audit runs in the right dir."""
        tool = PipAuditDockerTool(_make_config())
        cmd = tool.build_command(repo_path="/app")
        assert "-w" in cmd
        w_idx = cmd.index("-w")
        assert cmd[w_idx + 1] == "/app"

    def test_missing_repo_path_raises(self) -> None:
        tool = PipAuditDockerTool(_make_config())
        with pytest.raises(ValueError, match="docker_path"):
            tool.build_command(repo_path="")
