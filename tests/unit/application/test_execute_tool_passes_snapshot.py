"""Unit tests for snapshot handling in execute_tool_passes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from application.tools.scan_types.execution import execute_tool_passes
from application.tools.scan_types.models import ScanTypeConfig
from domain.tools.base import ToolResult
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext


class TestExecuteToolPassesSnapshot:
    def _make_config(
        self,
        arg_snapshots: dict[str, str] | None = None,
    ) -> ScanTypeConfig:
        """Create a ScanTypeConfig with optional arg_snapshots."""
        prompt = MagicMock()
        prompt.confirm.return_value = True
        return ScanTypeConfig(
            project_name="test",
            base_path="/tmp/test",
            tool_config=ToolExecutionConfig(noir_provider=None),
            run_id=1,
            prompt=prompt,
            arg_snapshots=arg_snapshots or {},
        )

    def _make_context(self) -> ExecutionContext:
        """Create a minimal ExecutionContext for testing."""
        return ExecutionContext(
            project_name="test",
            base_path="/tmp/test",
            repo=None,
            tool_config=ToolExecutionConfig(noir_provider=None),
            registry=MagicMock(),
            is_docker=False,
            execution_mode="scan",
        )

    def _make_execution_pass(
        self,
        label_suffix: str = "test",
    ) -> MagicMock:
        """Create a mock ExecutionPass."""
        pass_mock = MagicMock()
        pass_mock.label_suffix = label_suffix
        pass_mock.kwargs = {}
        pass_mock.cwd = None
        pass_mock.env = None
        return pass_mock

    def _make_tool_result(self) -> ToolResult:
        """Create a mock ToolResult."""
        return ToolResult(
            tool_name="test",
            success=True,
            output="",
            parsed_data={},
            output_files={},
            timestamp=ToolResult.now_iso(),
            duration_seconds=0.5,
        )

    def test_with_snapshot_and_command_config(self) -> None:
        """With snapshot + command_config, should call run_raw instead
        of build_execution_passes."""
        config = self._make_config(
            arg_snapshots={"zap": '[{"name":"--cmd","type":"flag"}]'}
        )
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "zap"
        mock_tool.build_execution_passes = MagicMock(
            side_effect=Exception("should not be called")
        )

        mock_executor = MagicMock()
        mock_result = self._make_tool_result()
        mock_executor.run_raw.return_value = mock_result

        command_config = SimpleNamespace(
            location="local",
            path="/usr/bin/zap",
        )

        result = execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=0,
            command_config=command_config,
        )

        assert result == mock_result
        assert mock_executor.run_raw.call_count == 1
        assert mock_tool.build_execution_passes.call_count == 0
        assert mock_executor.run.call_count == 0

    def test_without_snapshot_uses_default_path(self) -> None:
        """Without snapshot, should call build_execution_passes."""
        config = self._make_config(arg_snapshots={})
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "semgrep"

        pass_mock = self._make_execution_pass()
        mock_tool.build_execution_passes.return_value = [pass_mock]

        mock_result = self._make_tool_result()
        mock_tool.merge_pass_results.return_value = mock_result

        mock_executor = MagicMock()
        mock_executor.run.return_value = mock_result

        command_config = SimpleNamespace(
            location="local",
            path="/usr/bin/semgrep",
        )

        result = execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=0,
            command_config=command_config,
        )

        assert result == mock_result
        mock_tool.build_execution_passes.assert_called_once_with(context)
        mock_executor.run.assert_called_once()
        mock_executor.run_raw.assert_not_called()

    def test_with_snapshot_but_no_command_config(self) -> None:
        """With snapshot but command_config=None, should skip snapshot
        and use default path."""
        config = self._make_config(
            arg_snapshots={"zap": '[{"name":"--cmd","type":"flag"}]'}
        )
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "zap"

        pass_mock = self._make_execution_pass()
        mock_tool.build_execution_passes.return_value = [pass_mock]

        mock_result = self._make_tool_result()
        mock_tool.merge_pass_results.return_value = mock_result

        mock_executor = MagicMock()
        mock_executor.run.return_value = mock_result

        result = execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=0,
            command_config=None,
        )

        assert result == mock_result
        mock_tool.build_execution_passes.assert_called_once()
        mock_executor.run_raw.assert_not_called()

    def test_with_invalid_snapshot_json(self) -> None:
        """With invalid snapshot JSON, should log error and use
        default path."""
        config = self._make_config(arg_snapshots={"zap": "not-json"})
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "zap"

        pass_mock = self._make_execution_pass()
        mock_tool.build_execution_passes.return_value = [pass_mock]

        mock_result = self._make_tool_result()
        mock_tool.merge_pass_results.return_value = mock_result

        mock_executor = MagicMock()
        mock_executor.run.return_value = mock_result

        command_config = SimpleNamespace(
            location="local",
            path="/usr/bin/zap",
        )

        with patch("application.tools.scan_types.execution._log") as mock_log:
            result = execute_tool_passes(
                mock_tool,
                context,
                config,
                mock_executor,
                remaining_tools=0,
                command_config=command_config,
            )

        assert result == mock_result
        mock_log.exception.assert_called_once()
        mock_tool.build_execution_passes.assert_called_once()
        mock_executor.run_raw.assert_not_called()

    def test_snapshot_multiple_args(self) -> None:
        """Snapshot with multiple mixed arg types should be parsed
        and passed to run_raw."""
        snapshot = """[
            {"type": "flag", "name": "--verbose"},
            {"type": "string", "name": "--timeout", "value": "60"},
            {"type": "file", "name": "--config", "path": "/etc/app.json"}
        ]"""
        config = self._make_config(arg_snapshots={"tool": snapshot})
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "tool"

        mock_result = self._make_tool_result()
        mock_executor = MagicMock()
        mock_executor.run_raw.return_value = mock_result

        command_config = SimpleNamespace(
            location="docker",
            container=SimpleNamespace(name="container", tool_path="/app/tool"),
        )

        result = execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=0,
            command_config=command_config,
        )

        assert result == mock_result
        mock_executor.run_raw.assert_called_once()
        cmd_arg = mock_executor.run_raw.call_args[0][0]
        assert "--verbose" in cmd_arg
        assert "--timeout" in cmd_arg
        assert "60" in cmd_arg
        assert "--config" in cmd_arg
        assert "/etc/app.json" in cmd_arg

    def test_respects_confirm_rejection(self) -> None:
        """Should return None if prompt.confirm() returns False."""
        config = self._make_config(arg_snapshots={})
        config.prompt.confirm.return_value = False  # type: ignore[attr-defined]
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "test"

        mock_executor = MagicMock()

        result = execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=0,
            command_config=None,
        )

        assert result is None
        mock_executor.run_raw.assert_not_called()
        mock_executor.run.assert_not_called()

    def test_approves_remaining_tools(self) -> None:
        """Should call approve_all_remaining when remaining_tools > 0."""
        config = self._make_config(arg_snapshots={})
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "tool"

        pass_mock = self._make_execution_pass()
        mock_tool.build_execution_passes.return_value = [pass_mock]

        mock_result = self._make_tool_result()
        mock_tool.merge_pass_results.return_value = mock_result

        mock_executor = MagicMock()
        mock_executor.run.return_value = mock_result

        execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=5,
            command_config=None,
        )

        config.prompt.approve_all_remaining.assert_called_once()  # type: ignore[attr-defined]

    def test_with_empty_passes_list(self) -> None:
        """Should return None if build_execution_passes returns
        empty list."""
        config = self._make_config(arg_snapshots={})
        context = self._make_context()

        mock_tool = MagicMock()
        mock_tool.name = "tool"
        mock_tool.build_execution_passes.return_value = []

        mock_executor = MagicMock()

        result = execute_tool_passes(
            mock_tool,
            context,
            config,
            mock_executor,
            remaining_tools=0,
            command_config=None,
        )

        assert result is None
        mock_executor.run.assert_not_called()
