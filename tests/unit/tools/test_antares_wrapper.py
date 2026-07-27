"""Unit tests for Antares tool wrapper."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from core.config.schemas import Repository
from core.config.schemas.repo_service import RepoService
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


class TestAntaresLocalTool:
    """Tests for AntaresLocalTool."""

    def test_build_command_default(self) -> None:
        """Verify build_command with default mode."""
        tool = AntaresLocalTool()
        cmd = tool.build_command()
        assert cmd[0] == "antares"
        assert "tool" in cmd
        assert "sweep" in cmd
        assert "--stdin" in cmd
        assert "--format" in cmd
        assert "json" in cmd

    def test_build_command_query_mode(self) -> None:
        """Verify build_command with query mode."""
        tool = AntaresLocalTool()
        cmd = tool.build_command(mode="query")
        assert "query" in cmd
        assert "--stdin" in cmd

    @patch("shutil.which")
    def test_check_available_true(self, mock_which) -> None:
        """Verify check_available returns True when binary exists."""
        mock_which.return_value = "/usr/bin/antares"
        tool = AntaresLocalTool()
        assert tool.check_available() is True

    @patch("shutil.which")
    def test_check_available_false(self, mock_which) -> None:
        """Verify check_available returns False when binary missing."""
        mock_which.return_value = None
        tool = AntaresLocalTool()
        assert tool.check_available() is False

    @patch("infrastructure.tools.wrappers.local.antares.get_tool_version")
    def test_get_version(self, mock_version) -> None:
        """Verify get_version calls the version helper."""
        mock_version.return_value = "1.2.3"
        tool = AntaresLocalTool()
        version = tool.get_version()
        assert version == "1.2.3"
        mock_version.assert_called_once_with("antares")


class TestAntaresBuildExecutionPasses:
    """Tests for build_execution_passes method."""

    def _mock_config_manager(self):
        """Create a mock ConfigManager with resolved Antares config."""
        resolved_config = MagicMock()
        resolved_config.needs_shim = False
        resolved_config.endpoint_url = "http://localhost:8000"
        resolved_config.model = "test-model"
        resolved_config.timeout_seconds = 300

        mock_config_manager = MagicMock()
        mock_config_manager.return_value.global_config = MagicMock()

        return mock_config_manager, resolved_config

    @patch("core.config.manager.ConfigManager")
    def test_single_pass_returned(self, mock_config_manager, tmp_path) -> None:
        """Verify build_execution_passes returns exactly one pass."""
        mock_mgr, resolved_config = self._mock_config_manager()
        mock_config_manager.side_effect = mock_mgr

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)
            assert len(passes) == 1

    @patch("core.config.manager.ConfigManager")
    def test_pass_has_stdin_data(self, mock_config_manager, tmp_path) -> None:
        """Verify pass contains stdin_data with JSON payload."""
        mock_mgr, resolved_config = self._mock_config_manager()
        mock_config_manager.side_effect = mock_mgr

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)
            stdin_data = passes[0].stdin_data
            assert stdin_data is not None
            payload = json.loads(stdin_data)
            assert isinstance(payload, dict)
            assert "target" in payload

    @patch("core.config.manager.ConfigManager")
    def test_payload_contains_repo_path(self, mock_config_manager, tmp_path) -> None:
        """Verify stdin payload includes the repository path."""
        mock_mgr, resolved_config = self._mock_config_manager()
        mock_config_manager.side_effect = mock_mgr

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)
            stdin_data = passes[0].stdin_data
            assert stdin_data is not None
            payload = json.loads(stdin_data)
            assert payload["target"] == str(tmp_path)

    @patch("core.config.manager.ConfigManager")
    def test_label_suffix_is_repo_name(self, mock_config_manager, tmp_path) -> None:
        """Verify label_suffix uses repository name."""
        mock_mgr, resolved_config = self._mock_config_manager()
        mock_config_manager.side_effect = mock_mgr

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)
            assert passes[0].label_suffix == "test-repo"

    @patch("core.config.manager.ConfigManager")
    def test_empty_kwargs(self, mock_config_manager, tmp_path) -> None:
        """Verify kwargs are empty (payload goes via stdin)."""
        mock_mgr, resolved_config = self._mock_config_manager()
        mock_config_manager.side_effect = mock_mgr

        with patch(
            "infrastructure.llm.antares_config_resolver.resolve_antares_config",
            return_value=resolved_config,
        ):
            repo = _make_repo(str(tmp_path))
            ctx = _make_context(repo, str(tmp_path))
            tool = AntaresLocalTool()
            passes = tool.build_execution_passes(ctx)
            assert passes[0].kwargs == {}


class TestAntaresCountFindings:
    """Tests for count_findings method."""

    def test_count_from_summary(self) -> None:
        """Verify count_findings uses summary.total_findings."""
        tool = AntaresLocalTool()
        data = {
            "summary": {"total_findings": 5},
            "findings": [],
        }
        assert tool.count_findings(data) == 5

    def test_fallback_to_findings_length(self) -> None:
        """Verify count_findings falls back to len(findings)."""
        tool = AntaresLocalTool()
        data = {
            "summary": {},
            "findings": [{"title": "test"}],
        }
        assert tool.count_findings(data) == 1

    def test_zero_findings(self) -> None:
        """Verify count_findings returns 0 for empty data."""
        tool = AntaresLocalTool()
        data = {"summary": {}, "findings": []}
        assert tool.count_findings(data) == 0

    def test_missing_summary_and_findings(self) -> None:
        """Verify count_findings returns 0 when both missing."""
        tool = AntaresLocalTool()
        data = {}
        assert tool.count_findings(data) == 0

    def test_summary_takes_precedence(self) -> None:
        """Verify summary.total_findings takes precedence over findings."""
        tool = AntaresLocalTool()
        data = {
            "summary": {"total_findings": 3},
            "findings": [{"title": "a"}, {"title": "b"}],
        }
        assert tool.count_findings(data) == 3


class TestAntaresExitCodeHandling:
    """Tests for exit code handling and warning logging."""

    def test_parse_output_logs_failed_workers(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify parse_output logs warning for failed workers."""
        tool = AntaresLocalTool()
        output = json.dumps(
            {
                "summary": {
                    "total_findings": 1,
                    "failed_workers": 2,
                    "total_workers": 5,
                    "incomplete_reason": None,
                },
                "findings": [
                    {
                        "title": "test",
                        "file_path": "f.py",
                        "cwe_ids": ["CWE-1"],
                        "submission_rank": 1,
                        "likelihood_of_exploit": "High",
                    }
                ],
                "per_cwe_results": [],
            }
        )
        with caplog.at_level(logging.WARNING):
            result = tool.parse_output(output, {})
        assert "failed_workers" in caplog.text or "2" in caplog.text
        assert result["findings"]

    def test_parse_output_logs_incomplete_reason(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify parse_output logs warning for incomplete reason."""
        tool = AntaresLocalTool()
        output = json.dumps(
            {
                "summary": {
                    "total_findings": 0,
                    "failed_workers": 0,
                    "incomplete_reason": "endpoint unreachable",
                },
                "findings": [],
                "per_cwe_results": [],
            }
        )
        with caplog.at_level(logging.WARNING):
            tool.parse_output(output, {})
        assert "endpoint unreachable" in caplog.text

    def test_parse_output_logs_per_cwe_errors(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify parse_output logs warnings for per-CWE errors."""
        tool = AntaresLocalTool()
        output = json.dumps(
            {
                "summary": {"total_findings": 0, "failed_workers": 1},
                "findings": [],
                "per_cwe_results": [
                    {"cwe_id": "CWE-78", "error_message": "model timeout"},
                    {"cwe_id": "CWE-89", "error_message": None},
                ],
            }
        )
        with caplog.at_level(logging.WARNING):
            tool.parse_output(output, {})
        assert "CWE-78" in caplog.text
        assert "model timeout" in caplog.text
        assert "CWE-89" not in caplog.text

    def test_parse_output_no_warnings_on_clean_scan(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify parse_output produces no warnings on clean scan."""
        tool = AntaresLocalTool()
        output = json.dumps(
            {
                "summary": {
                    "total_findings": 2,
                    "failed_workers": 0,
                    "incomplete_reason": None,
                },
                "findings": [
                    {
                        "title": "t",
                        "file_path": "f",
                        "cwe_ids": ["CWE-1"],
                        "submission_rank": 1,
                        "likelihood_of_exploit": "High",
                    }
                ],
                "per_cwe_results": [],
            }
        )
        with caplog.at_level(logging.WARNING):
            tool.parse_output(output, {})
        assert caplog.text == ""

    def test_parse_output_handles_invalid_json(self) -> None:
        """Verify parse_output handles invalid JSON gracefully."""
        tool = AntaresLocalTool()
        result = tool.parse_output("not json", {})
        assert "error" in result
