"""Unit tests for Antares shim lifecycle integration."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

from core.config.schemas import Repository
from core.config.schemas.repo_service import RepoService
from domain.tools.base import ToolResult
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.llm.antares_config_resolver import AntaresResolvedConfig
from infrastructure.tools.wrappers.local.antares import AntaresLocalTool


def _make_repo(path: str) -> Repository:
    """Create a test repository."""
    return Repository.model_construct(
        name="test-repo",
        type=["app"],
        path=path,
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=[],
        ignore_dirs=[],
        dependencies_file="",
    )


def _make_context(
    repo: Repository, repo_path: str, tool_config=None
) -> ExecutionContext:
    """Create a test execution context."""
    registry = MagicMock()
    registry.get_service_path.return_value = repo_path
    service = (
        repo.services[0]
        if repo.services
        else RepoService.model_construct(name="default")
    )
    return ExecutionContext(
        project_name="test",
        base_path="/tmp",
        repo=repo,
        service=service,
        tool_config=tool_config or ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=False,
    )


class TestAntaresShimLifecycle:
    """Tests for shim lifecycle in Antares wrapper."""

    @patch("infrastructure.tools.wrappers.base.antares.CompletionsShim")
    def test_shim_started_when_ollama_provider(self, mock_shim_class, tmp_path) -> None:
        """Verify shim is created and started for Ollama provider."""
        mock_shim_instance = MagicMock()
        mock_shim_instance.start.return_value = "http://127.0.0.1:12345"
        mock_shim_class.return_value = mock_shim_instance

        resolved_config = AntaresResolvedConfig(
            endpoint_url="http://localhost:11434",
            model="neural-chat",
            needs_shim=True,
            ollama_base_url="http://localhost:11434",
            timeout_seconds=300,
            max_cwes=None,
            workers=None,
        )
        repo = _make_repo(str(tmp_path))
        tool_config = ToolExecutionConfig(
            noir_provider=None,
            antares_config=resolved_config,
        )
        ctx = _make_context(repo, str(tmp_path), tool_config=tool_config)
        tool = AntaresLocalTool()
        passes = tool.build_execution_passes(ctx)

        mock_shim_class.assert_called_once_with(
            "http://localhost:11434", "neural-chat", 300
        )
        mock_shim_instance.start.assert_called_once()

        assert passes[0].env is not None
        assert passes[0].env["ANTARES_ENDPOINT"] == "http://127.0.0.1:12345"

    @patch("infrastructure.tools.wrappers.base.antares.CompletionsShim")
    def test_no_shim_when_direct_provider(self, mock_shim_class, tmp_path) -> None:
        """Verify shim is not created for direct providers."""
        resolved_config = AntaresResolvedConfig(
            endpoint_url="http://direct-llm.local:8000",
            model="my-model",
            needs_shim=False,
            ollama_base_url=None,
            timeout_seconds=300,
            max_cwes=None,
            workers=None,
        )
        repo = _make_repo(str(tmp_path))
        tool_config = ToolExecutionConfig(
            noir_provider=None,
            antares_config=resolved_config,
        )
        ctx = _make_context(repo, str(tmp_path), tool_config=tool_config)
        tool = AntaresLocalTool()
        passes = tool.build_execution_passes(ctx)

        mock_shim_class.assert_not_called()

        assert passes[0].env is not None
        assert passes[0].env["ANTARES_ENDPOINT"] == "http://direct-llm.local:8000"

    def test_shim_stopped_in_merge_pass_results(self) -> None:
        """Verify shim.stop() is called in merge_pass_results."""
        mock_shim = MagicMock()

        tool = AntaresLocalTool()
        tool._shim = mock_shim

        result = ToolResult(
            tool_name="antares",
            success=True,
            output="{}",
            parsed_data={"findings": []},
            output_files={},
            timestamp="2025-01-01T00:00:00Z",
            duration_seconds=1.0,
        )

        tool.merge_pass_results([result])

        mock_shim.stop.assert_called_once()
        assert tool._shim is None

    def test_shim_stopped_even_on_error(self) -> None:
        """Verify shim.stop() is called even if merge fails."""
        mock_shim = MagicMock()

        tool = AntaresLocalTool()
        tool._shim = mock_shim

        results = cast(list[ToolResult], [])

        try:
            tool.merge_pass_results(results)
        except IndexError:
            pass

        mock_shim.stop.assert_called_once()
        assert tool._shim is None

    @patch("infrastructure.tools.wrappers.base.antares.CompletionsShim")
    def test_env_vars_set_from_config(self, mock_shim_class, tmp_path) -> None:
        """Verify all Antares env vars are set from resolved config."""
        mock_shim_instance = MagicMock()
        mock_shim_instance.start.return_value = "http://127.0.0.1:54321"
        mock_shim_class.return_value = mock_shim_instance

        resolved_config = AntaresResolvedConfig(
            endpoint_url="http://localhost:11434",
            model="mistral",
            needs_shim=True,
            ollama_base_url="http://localhost:11434",
            timeout_seconds=600,
            max_cwes=None,
            workers=None,
        )
        repo = _make_repo(str(tmp_path))
        tool_config = ToolExecutionConfig(
            noir_provider=None,
            antares_config=resolved_config,
        )
        ctx = _make_context(repo, str(tmp_path), tool_config=tool_config)
        tool = AntaresLocalTool()
        passes = tool.build_execution_passes(ctx)

        env = passes[0].env
        assert env is not None
        assert env["ANTARES_ENDPOINT"] == "http://127.0.0.1:54321"
        assert env["ANTARES_MODEL"] == "mistral"
        assert env["ANTARES_REMOTE_TIMEOUT_SECONDS"] == "600"

    def test_env_vars_without_shim(self, tmp_path) -> None:
        """Verify env vars are still set when shim is not needed."""
        resolved_config = AntaresResolvedConfig(
            endpoint_url="https://api.anthropic.com",
            model="claude-opus",
            needs_shim=False,
            ollama_base_url=None,
            timeout_seconds=120,
            max_cwes=None,
            workers=None,
        )
        repo = _make_repo(str(tmp_path))
        tool_config = ToolExecutionConfig(
            noir_provider=None,
            antares_config=resolved_config,
        )
        ctx = _make_context(repo, str(tmp_path), tool_config=tool_config)
        tool = AntaresLocalTool()
        passes = tool.build_execution_passes(ctx)

        env = passes[0].env
        assert env is not None
        assert env["ANTARES_ENDPOINT"] == "https://api.anthropic.com"
        assert env["ANTARES_MODEL"] == "claude-opus"
        assert env["ANTARES_REMOTE_TIMEOUT_SECONDS"] == "120"

    def test_no_shim_set_when_not_needed(self, tmp_path) -> None:
        """Verify _shim remains None when shim is not needed."""
        resolved_config = AntaresResolvedConfig(
            endpoint_url="https://api.anthropic.com",
            model="claude-opus",
            needs_shim=False,
            ollama_base_url=None,
            timeout_seconds=120,
            max_cwes=None,
            workers=None,
        )
        repo = _make_repo(str(tmp_path))
        tool_config = ToolExecutionConfig(
            noir_provider=None,
            antares_config=resolved_config,
        )
        ctx = _make_context(repo, str(tmp_path), tool_config=tool_config)
        tool = AntaresLocalTool()
        tool.build_execution_passes(ctx)

        assert tool._shim is None
