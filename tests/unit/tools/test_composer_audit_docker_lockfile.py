"""Unit tests for ComposerAuditDockerTool.build_execution_passes lockfile failover."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.config.schemas import Repository
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.docker.composer_audit import (
    ComposerAuditDockerTool,
)
from infrastructure.tools.wrappers.utils.install_fallback import reset_attempted


def _make_config(container_name: str = "php-container") -> MagicMock:
    cfg = MagicMock()
    cfg.container.name = container_name
    cfg.container.tool_path = "/usr/bin/composer"
    return cfg


def _make_repo(docker_path: str = "/app") -> Repository:
    return Repository.model_construct(
        name="my-php-repo",
        type=["api"],
        path="",
        docker_path=docker_path,
        container_name="php-container",
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
        is_docker=True,
    )


class TestComposerAuditDockerLockfileFailover:
    def setup_method(self) -> None:
        reset_attempted()

    def test_returns_pass_when_lockfile_exists_in_container(self) -> None:
        def _mock(cmd, **kwargs):
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            repo = _make_repo()
            ctx = _make_context(repo, "/app")
            passes = ComposerAuditDockerTool(_make_config()).build_execution_passes(ctx)

        assert len(passes) == 1
        assert passes[0].kwargs["repo_path"] == "/app"

    def test_attempts_docker_install_when_lockfile_missing(self) -> None:
        install_calls = []

        def _mock(cmd, **kwargs):
            if "test" in cmd:
                rc = 1 if not install_calls else 0
                return type("R", (), {"returncode": rc, "stdout": "", "stderr": ""})()
            install_calls.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            repo = _make_repo()
            ctx = _make_context(repo, "/app")
            ComposerAuditDockerTool(_make_config()).build_execution_passes(ctx)

        assert len(install_calls) == 1
        assert install_calls[0][0] == "docker"
        assert "exec" in install_calls[0]

    def test_skips_when_docker_install_fails(self) -> None:
        def _mock(cmd, **kwargs):
            if "test" in cmd:
                return type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            repo = _make_repo()
            ctx = _make_context(repo, "/app")
            passes = ComposerAuditDockerTool(_make_config()).build_execution_passes(ctx)

        assert passes == []

    def test_install_uses_no_scripts_flag(self) -> None:
        install_calls = []

        def _mock(cmd, **kwargs):
            if "test" in cmd:
                rc = 1 if not install_calls else 0
                return type("R", (), {"returncode": rc, "stdout": "", "stderr": ""})()
            install_calls.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            repo = _make_repo()
            ctx = _make_context(repo, "/app")
            ComposerAuditDockerTool(_make_config()).build_execution_passes(ctx)

        assert install_calls, "install should have been called"
        assert "--no-scripts" in install_calls[0]

    def test_install_uses_container_name(self) -> None:
        install_calls = []

        def _mock(cmd, **kwargs):
            if "test" in cmd:
                rc = 1 if not install_calls else 0
                return type("R", (), {"returncode": rc, "stdout": "", "stderr": ""})()
            install_calls.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            repo = _make_repo()
            ctx = _make_context(repo, "/app")
            ComposerAuditDockerTool(
                _make_config(container_name="php-container")
            ).build_execution_passes(ctx)

        assert "php-container" in install_calls[0]

    def test_cwd_is_none_for_docker_pass(self) -> None:
        def _mock(cmd, **kwargs):
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            side_effect=_mock,
        ):
            repo = _make_repo()
            ctx = _make_context(repo, "/app")
            passes = ComposerAuditDockerTool(_make_config()).build_execution_passes(ctx)

        assert passes[0].cwd is None
