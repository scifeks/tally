"""Unit tests for ToolExecutor.run_raw and raw_cmd support."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.tools.executor import ToolExecutor
from domain.tools.base import ToolResult
from infrastructure.tools.cli_runner import CliToolRunner


class TestExecutorRunRaw:
    @pytest.fixture
    def mock_subprocess_runner(self) -> MagicMock:
        mock_runner = MagicMock()
        mock_runner.run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0,
        )
        return mock_runner

    @pytest.fixture
    def mock_prompt(self) -> MagicMock:
        mock = MagicMock()
        mock.confirm.return_value = True
        return mock

    @pytest.fixture
    def executor(
        self,
        mock_subprocess_runner: MagicMock,
        mock_prompt: MagicMock,
    ) -> ToolExecutor:
        with patch("application.tools.executor.sanitize_command"):
            with patch(
                "application.tools.executor.ProjectPaths.from_canonical"
            ) as mock_paths:
                mock_paths_instance = MagicMock()
                mock_paths_instance.tool_output_dir.return_value = Path("/tmp/output")
                mock_paths.return_value = mock_paths_instance
                executor = ToolExecutor(
                    project_name="test",
                    base_path=Path("/tmp/test"),
                    prompt=mock_prompt,
                    cli_tool_runner=CliToolRunner(mock_subprocess_runner),
                    reporter=None,
                )
                return executor

    def test_run_raw_bypasses_build_command(
        self,
        executor: ToolExecutor,
    ) -> None:
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.build_command = MagicMock(
            side_effect=Exception("should not be called")
        )
        mock_tool.parse_output.return_value = {"findings": []}
        mock_tool.findings_exit_ok = False

        raw_cmd = ["docker", "exec", "c", "t", "--flag"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.run_raw(raw_cmd, mock_tool)

        assert isinstance(result, ToolResult)
        assert result.tool_name == "test_tool"

    def test_run_raw_returns_tool_result(
        self,
        executor: ToolExecutor,
    ) -> None:
        mock_tool = MagicMock()
        mock_tool.name = "gitleaks"
        mock_tool.parse_output.return_value = {"leaks": []}
        mock_tool.findings_exit_ok = True

        raw_cmd = ["gitleaks", "detect", "--source", "/repo"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.run_raw(raw_cmd, mock_tool)

        assert isinstance(result, ToolResult)
        assert result.tool_name == "gitleaks"
        assert result.success is True
        assert result.parsed_data == {"leaks": []}

    def test_execute_with_raw_cmd_ignores_kwargs(
        self,
        executor: ToolExecutor,
    ) -> None:
        mock_tool = MagicMock()
        mock_tool.name = "tool"
        mock_tool.build_command = MagicMock(
            side_effect=Exception("should not be called")
        )
        mock_tool.parse_output.return_value = {}
        mock_tool.findings_exit_ok = False

        raw_cmd = ["cmd", "arg"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.execute(
                mock_tool,
                auto_approve=True,
                raw_cmd=raw_cmd,
                ignored_kwarg="value",
            )

        assert isinstance(result, ToolResult)

    def test_execute_without_raw_cmd_calls_build_command(
        self,
        executor: ToolExecutor,
    ) -> None:
        mock_tool = MagicMock()
        mock_tool.name = "semgrep"
        mock_tool.build_command.return_value = ["semgrep", "scan"]
        mock_tool.parse_output.return_value = {}
        mock_tool.findings_exit_ok = False

        with patch("application.tools.executor.sanitize_command"):
            result = executor.execute(
                mock_tool,
                auto_approve=True,
                config="p/security-audit",
            )

        assert isinstance(result, ToolResult)
        mock_tool.build_command.assert_called_once_with(config="p/security-audit")

    def test_run_raw_respects_tool_timeout(
        self,
        executor: ToolExecutor,
        mock_subprocess_runner: MagicMock,
    ) -> None:
        mock_tool = MagicMock()
        mock_tool.name = "slow_tool"
        mock_tool.timeout = 1800
        mock_tool.parse_output.return_value = {}
        mock_tool.findings_exit_ok = False

        raw_cmd = ["slow_tool", "--deep-scan"]
        with patch("application.tools.executor.sanitize_command"):
            executor.run_raw(raw_cmd, mock_tool)

        call_kwargs = mock_subprocess_runner.run.call_args[1]
        assert call_kwargs["timeout"] == 1800

    def test_run_raw_default_label_is_custom(
        self,
        executor: ToolExecutor,
        mock_subprocess_runner: MagicMock,
    ) -> None:
        mock_subprocess_runner.run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0,
        )
        mock_tool = MagicMock()
        mock_tool.name = "tool"
        mock_tool.parse_output.return_value = {}
        mock_tool.findings_exit_ok = False

        raw_cmd = ["cmd"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.run_raw(raw_cmd, mock_tool)

        assert isinstance(result, ToolResult)

    def test_exit_code_3_success_when_in_findings_exit_codes(
        self,
        executor: ToolExecutor,
        mock_subprocess_runner: MagicMock,
    ) -> None:
        mock_subprocess_runner.run.return_value = MagicMock(
            stdout='{"advisories": {}}',
            stderr="",
            returncode=3,
        )
        mock_tool = MagicMock()
        mock_tool.name = "composer-audit"
        mock_tool.parse_output.return_value = {"vulnerabilities": []}
        mock_tool.findings_exit_ok = True
        mock_tool.findings_exit_codes = frozenset({1, 2, 3})

        raw_cmd = ["composer", "audit", "--format=json"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.run_raw(raw_cmd, mock_tool)

        assert result.success is True

    def test_exit_code_3_failure_when_not_in_findings_exit_codes(
        self,
        executor: ToolExecutor,
        mock_subprocess_runner: MagicMock,
    ) -> None:
        mock_subprocess_runner.run.return_value = MagicMock(
            stdout="error output",
            stderr="",
            returncode=3,
        )
        mock_tool = MagicMock()
        mock_tool.name = "some-tool"
        mock_tool.parse_output.return_value = {}
        mock_tool.findings_exit_ok = True
        mock_tool.findings_exit_codes = frozenset({1})

        raw_cmd = ["some-tool", "scan"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.run_raw(raw_cmd, mock_tool)

        assert result.success is False

    def test_exit_code_2_success_when_in_findings_exit_codes(
        self,
        executor: ToolExecutor,
        mock_subprocess_runner: MagicMock,
    ) -> None:
        mock_subprocess_runner.run.return_value = MagicMock(
            stdout='{"advisories": {}, "abandoned": {}}',
            stderr="",
            returncode=2,
        )
        mock_tool = MagicMock()
        mock_tool.name = "composer-audit"
        mock_tool.parse_output.return_value = {"vulnerabilities": []}
        mock_tool.findings_exit_ok = True
        mock_tool.findings_exit_codes = frozenset({1, 2, 3})

        raw_cmd = ["composer", "audit", "--format=json"]
        with patch("application.tools.executor.sanitize_command"):
            result = executor.run_raw(raw_cmd, mock_tool)

        assert result.success is True
