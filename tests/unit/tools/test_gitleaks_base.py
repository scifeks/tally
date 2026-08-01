"""Unit tests for infrastructure.tools.wrappers.base.gitleaks."""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

from core.config.schemas import Repository
from core.config.schemas.repo_service import RepoService
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.base.gitleaks import BaseGitleaksTool


def _make_repo(path: str) -> Repository:
    return Repository.model_construct(
        name="test-repo",
        type=["app"],
        path=path,
        docker_path="/repo",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=[],
        ignore_dirs=[],
        dependencies_file="",
    )


def _make_service() -> RepoService:
    return RepoService.model_construct(
        name="default",
        docker_path="/app",
        container_name="",
    )


def _make_context(
    repo: Repository,
    service: RepoService,
    is_docker: bool = False,
) -> ExecutionContext:
    registry = MagicMock()
    registry.get_service_path.return_value = repo.path
    return ExecutionContext(
        project_name="test",
        base_path="/tmp",
        repo=repo,
        service=service,
        tool_config=ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=is_docker,
    )


class TestBaseGitleaksToolBuildExecutionPasses:
    def test_local_tool_creates_temp_file_for_config(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        service = _make_service()
        context = _make_context(repo, service, is_docker=False)

        tool = BaseGitleaksTool()
        temp_fd = 999
        temp_path = "/tmp/tally_gitleaks_test.toml"

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (temp_fd, temp_path)
            with patch("os.fdopen", mock_open()):
                passes = tool.build_execution_passes(context)

        mock_mkstemp.assert_called_once()
        call_kwargs = mock_mkstemp.call_args[1]
        assert call_kwargs.get("suffix") == ".toml"
        assert "tally_gitleaks_" in call_kwargs.get("prefix", "")

        assert len(passes) == 2
        for pass_obj in passes:
            config_path = pass_obj.kwargs.get("config_path")
            assert config_path == temp_path
            assert not config_path.startswith("/app/")
            assert not config_path.startswith("/repo/")

    def test_docker_tool_uses_container_path_for_config(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        service = _make_service()
        context = _make_context(repo, service, is_docker=True)

        tool = BaseGitleaksTool()

        with patch("pathlib.Path.write_text") as mock_write:
            passes = tool.build_execution_passes(context)

        mock_write.assert_called_once()
        call_args = mock_write.call_args[0]
        toml_content = call_args[0]
        assert ".git" in toml_content

        assert len(passes) == 2
        for pass_obj in passes:
            config_path = pass_obj.kwargs.get("config_path")
            assert config_path == "/app/.tally_gitleaks.toml"

    def test_both_passes_have_repo_path(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        service = _make_service()
        context = _make_context(repo, service, is_docker=False)

        tool = BaseGitleaksTool()

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (999, "/tmp/test.toml")
            with patch("os.fdopen", mock_open()):
                passes = tool.build_execution_passes(context)

        assert len(passes) == 2
        assert passes[0].kwargs.get("repo_path") == str(tmp_path)
        assert passes[1].kwargs.get("repo_path") == str(tmp_path)

    def test_execution_passes_have_correct_labels(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        service = _make_service()
        context = _make_context(repo, service, is_docker=False)

        tool = BaseGitleaksTool()

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (999, "/tmp/test.toml")
            with patch("os.fdopen", mock_open()):
                passes = tool.build_execution_passes(context)

        assert len(passes) == 2
        assert "dir" in passes[0].label_suffix
        assert "git" in passes[1].label_suffix
        assert "test-repo" in passes[0].label_suffix
        assert "test-repo" in passes[1].label_suffix

    def test_execution_passes_have_correct_scan_types(self, tmp_path) -> None:
        repo = _make_repo(str(tmp_path))
        service = _make_service()
        context = _make_context(repo, service, is_docker=False)

        tool = BaseGitleaksTool()

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (999, "/tmp/test.toml")
            with patch("os.fdopen", mock_open()):
                passes = tool.build_execution_passes(context)

        assert passes[0].kwargs.get("scan_type") == "dir"
        assert passes[1].kwargs.get("scan_type") == "git"
