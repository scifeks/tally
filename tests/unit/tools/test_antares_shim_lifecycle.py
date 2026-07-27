"""Unit tests for Antares shim lifecycle integration."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

from core.config.schemas import Repository
from core.config.schemas.repo_service import RepoService
from domain.tools.base import ToolResult
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
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

    @patch("core.config.manager.ConfigManager")
    @patch("infrastructure.tools.wrappers.base.antares.CompletionsShim")
    def test_shim_started_when_ollama_provider(
        self, mock_shim_class, mock_config_manager, tmp_path
    ) -> None:
        """Verify shim is created and started for Ollama provider."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config_manager.return_value.global_config = mock_config

        mock_shim_instance = MagicMock()
        mock_shim_instance.start.return_value = "http://127.0.0.1:12345"
        mock_shim_class.return_value = mock_shim_instance

        resolved_config = MagicMock()
        resolved_config.needs_shim = True
        resolved_config.ollama_base_url = "http://localhost:11434"
        resolved_config.model = "neural-chat"
        resolved_config.endpoint_url = "http://localhost:11434"
        resolved_config.timeout_seconds = 300

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)

            # Verify shim was created with correct args
            mock_shim_class.assert_called_once_with(
                "http://localhost:11434", "neural-chat"
            )
            mock_shim_instance.start.assert_called_once()

            # Verify endpoint in env is the shim URL
            assert passes[0].env is not None
            assert passes[0].env["ANTARES_ENDPOINT"] == "http://127.0.0.1:12345"

    @patch("core.config.manager.ConfigManager")
    @patch("infrastructure.tools.wrappers.base.antares.CompletionsShim")
    def test_no_shim_when_direct_provider(
        self, mock_shim_class, mock_config_manager, tmp_path
    ) -> None:
        """Verify shim is not created for direct providers."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config_manager.return_value.global_config = mock_config

        resolved_config = MagicMock()
        resolved_config.needs_shim = False
        resolved_config.endpoint_url = "http://direct-llm.local:8000"
        resolved_config.model = "my-model"
        resolved_config.timeout_seconds = 300

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)

            # Verify shim was NOT created
            mock_shim_class.assert_not_called()

            # Verify endpoint in env is the direct URL
            assert passes[0].env is not None
            assert passes[0].env["ANTARES_ENDPOINT"] == "http://direct-llm.local:8000"

    def test_shim_stopped_in_merge_pass_results(self) -> None:
        """Verify shim.stop() is called in merge_pass_results."""
        # Setup a mock shim
        mock_shim = MagicMock()

        tool = AntaresLocalTool()
        tool._shim = mock_shim

        # Create mock results
        result = MagicMock(spec=ToolResult)
        results = cast(list[ToolResult], [result])

        # Call merge_pass_results
        output = tool.merge_pass_results(results)

        # Verify shim was stopped
        mock_shim.stop.assert_called_once()
        assert tool._shim is None
        assert output is result

    def test_shim_stopped_even_on_error(self) -> None:
        """Verify shim.stop() is called even if merge fails."""
        # Setup a mock shim
        mock_shim = MagicMock()

        tool = AntaresLocalTool()
        tool._shim = mock_shim

        # Create mock results that will fail
        results = cast(list[ToolResult], [])

        # Call merge_pass_results with empty results (will raise IndexError)
        try:
            tool.merge_pass_results(results)
        except IndexError:
            pass

        # Verify shim was still stopped
        mock_shim.stop.assert_called_once()
        assert tool._shim is None

    @patch("core.config.manager.ConfigManager")
    @patch("infrastructure.tools.wrappers.base.antares.CompletionsShim")
    def test_env_vars_set_from_config(
        self, mock_shim_class, mock_config_manager, tmp_path
    ) -> None:
        """Verify all Antares env vars are set from resolved config."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config_manager.return_value.global_config = mock_config

        mock_shim_instance = MagicMock()
        mock_shim_instance.start.return_value = "http://127.0.0.1:54321"
        mock_shim_class.return_value = mock_shim_instance

        resolved_config = MagicMock()
        resolved_config.needs_shim = True
        resolved_config.ollama_base_url = "http://localhost:11434"
        resolved_config.model = "mistral"
        resolved_config.endpoint_url = "http://localhost:11434"
        resolved_config.timeout_seconds = 600

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)

            # Verify all env vars are set
            env = passes[0].env
            assert env is not None
            assert env["ANTARES_ENDPOINT"] == "http://127.0.0.1:54321"
            assert env["ANTARES_MODEL"] == "mistral"
            assert env["ANTARES_REMOTE_TIMEOUT_SECONDS"] == "600"

    @patch("core.config.manager.ConfigManager")
    def test_env_vars_without_shim(self, mock_config_manager, tmp_path) -> None:
        """Verify env vars are still set when shim is not needed."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config_manager.return_value.global_config = mock_config

        resolved_config = MagicMock()
        resolved_config.needs_shim = False
        resolved_config.endpoint_url = "https://api.anthropic.com"
        resolved_config.model = "claude-opus"
        resolved_config.timeout_seconds = 120

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)

            # Verify env vars are set with direct endpoint
            env = passes[0].env
            assert env is not None
            assert env["ANTARES_ENDPOINT"] == "https://api.anthropic.com"
            assert env["ANTARES_MODEL"] == "claude-opus"
            assert env["ANTARES_REMOTE_TIMEOUT_SECONDS"] == "120"

    @patch("core.config.manager.ConfigManager")
    def test_no_shim_set_when_not_needed(self, mock_config_manager, tmp_path) -> None:
        """Verify _shim remains None when shim is not needed."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config_manager.return_value.global_config = mock_config

        resolved_config = MagicMock()
        resolved_config.needs_shim = False
        resolved_config.endpoint_url = "https://api.anthropic.com"
        resolved_config.model = "claude-opus"
        resolved_config.timeout_seconds = 120

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            tool.build_execution_passes(ctx)

            # Verify _shim is still None
            assert tool._shim is None
