"""Unit tests for ComposerAuditLocalTool.build_execution_passes lockfile failover."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.config.schemas import Repository
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.composer_audit import ComposerAuditLocalTool
from infrastructure.tools.wrappers.utils.install_fallback import reset_attempted


def _make_repo(path: str) -> Repository:
    return Repository.model_construct(
        name="my-php-repo",
        type=["api"],
        path=path,
        docker_path="",
        container_name="",
        languages=["php"],
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
        tool_config=ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=False,
    )


class TestComposerAuditLocalLockfileFailover:
    def setup_method(self) -> None:
        reset_attempted()

    def test_skips_when_no_composer_json(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        ctx = _make_context(repo, str(tmp_path))
        passes = ComposerAuditLocalTool().build_execution_passes(ctx)
        assert passes == []

    def test_returns_pass_when_both_files_exist(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")
        (tmp_path / "composer.lock").write_text("{}")
        repo = _make_repo(str(tmp_path))
        ctx = _make_context(repo, str(tmp_path))
        passes = ComposerAuditLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].kwargs["repo_path"] == str(tmp_path)

    def test_attempts_composer_install_when_lock_missing(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")

        def _create_lockfile(cmd, **kwargs):
            (tmp_path / "composer.lock").write_text("{}")
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_create_lockfile,
        ) as mock_run:
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            passes = ComposerAuditLocalTool().build_execution_passes(ctx)

        mock_run.assert_called_once()
        assert len(passes) == 1

    def test_skips_when_composer_install_fails(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            passes = ComposerAuditLocalTool().build_execution_passes(ctx)

        assert passes == []

    def test_install_command_is_no_scripts(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")
        captured_cmd = []

        def _capture(cmd, **kwargs):
            if "test" not in cmd:
                captured_cmd.append(cmd)
            (tmp_path / "composer.lock").write_text("{}")
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_capture,
        ):
            ComposerAuditLocalTool().build_execution_passes(
                _make_context(_make_repo(str(tmp_path)), str(tmp_path))
            )

        assert any("--no-scripts" in cmd for cmd in captured_cmd)
        assert any("install" in cmd for cmd in captured_cmd)

    def test_cwd_is_repo_path(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")
        (tmp_path / "composer.lock").write_text("{}")
        repo = _make_repo(str(tmp_path))
        ctx = _make_context(repo, str(tmp_path))
        passes = ComposerAuditLocalTool().build_execution_passes(ctx)
        assert passes[0].cwd == str(tmp_path)
