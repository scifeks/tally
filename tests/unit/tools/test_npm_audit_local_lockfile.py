"""Unit tests for NpmAuditLocalTool.build_execution_passes lockfile failover."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.npm_audit import NpmAuditLocalTool
from infrastructure.tools.wrappers.utils.install_fallback import reset_attempted


def _make_repo(path: str) -> Repository:
    return Repository.model_construct(
        name="my-repo",
        type=["api"],
        path=path,
        docker_path="",
        container_name="",
        languages=["javascript"],
        base_urls=[],
        test_dirs=[],
        ignore_dirs=[],
        dependencies_file="",
    )


def _make_context(repo: Repository, repo_path: str) -> ExecutionContext:
    registry = MagicMock()
    registry.get_repo_path.return_value = repo_path
    return ExecutionContext(
        project_name="test",
        base_path="/tmp",
        repo=repo,
        config_manager=MagicMock(),
        registry=registry,
        is_docker=False,
    )


class TestNpmAuditLocalLockfileFailover:
    def setup_method(self) -> None:
        reset_attempted()

    def test_skips_when_no_package_json(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        ctx = _make_context(repo, str(tmp_path))
        tool = NpmAuditLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert passes == []

    def test_returns_pass_when_lockfile_exists(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "package-lock.json").write_text("{}")
        repo = _make_repo(str(tmp_path))
        ctx = _make_context(repo, str(tmp_path))
        tool = NpmAuditLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].kwargs["repo_path"] == str(tmp_path)

    def test_attempts_npm_install_when_lockfile_missing(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")

        def _create_lockfile(cmd, **kwargs):
            (tmp_path / "package-lock.json").write_text("{}")
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_create_lockfile,
        ) as mock_run:
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = NpmAuditLocalTool()
            passes = tool.build_execution_passes(ctx)

        mock_run.assert_called_once()
        assert len(passes) == 1

    def test_skips_when_npm_install_fails(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = NpmAuditLocalTool()
            passes = tool.build_execution_passes(ctx)

        assert passes == []

    def test_npm_install_command_is_package_lock_only(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        captured_cmd = []

        def _capture(cmd, **kwargs):
            if "test" not in cmd:
                captured_cmd.append(cmd)
            (tmp_path / "package-lock.json").write_text("{}")
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_capture,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            NpmAuditLocalTool().build_execution_passes(ctx)

        assert any("--package-lock-only" in cmd for cmd in captured_cmd)

    def test_cwd_is_repo_path(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "package-lock.json").write_text("{}")
        repo = _make_repo(str(tmp_path))
        ctx = _make_context(repo, str(tmp_path))
        passes = NpmAuditLocalTool().build_execution_passes(ctx)
        assert passes[0].cwd == str(tmp_path)
