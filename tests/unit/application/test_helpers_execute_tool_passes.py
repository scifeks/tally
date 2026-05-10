"""Unit tests for execute_tool_passes in application/tools/scan_types/execution.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.tools.scan_types.execution import execute_tool_passes
from application.tools.scan_types.models import ScanTypeConfig
from domain.tools.execution_config import ToolExecutionConfig


def _make_prompt(confirm_return: bool = True) -> MagicMock:
    prompt = MagicMock()
    prompt.confirm.return_value = confirm_return
    prompt.approve_all_remaining.return_value = None
    return prompt


def _make_config(prompt: MagicMock | None = None, **overrides) -> ScanTypeConfig:
    defaults: dict = dict(
        project_name="proj",
        base_path="/tmp/proj",
        tool_config=ToolExecutionConfig(noir_provider=None),
        run_id=1,
        prompt=prompt or _make_prompt(),
    )
    defaults.update(overrides)
    return ScanTypeConfig(**defaults)


def _make_tool(name: str = "mytool") -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.build_execution_passes.return_value = [MagicMock()]
    tool.merge_pass_results.return_value = MagicMock()
    return tool


class TestExecuteToolPassesApproval:
    def test_confirm_returns_false_skips_execution(self) -> None:
        """When prompt.confirm() returns False, tool is not run."""
        prompt = _make_prompt(confirm_return=False)
        config = _make_config(prompt=prompt)
        tool = _make_tool()
        executor = MagicMock()

        result = execute_tool_passes(tool, MagicMock(), config, executor)

        assert result is None
        executor.run.assert_not_called()

    def test_confirm_returns_true_runs_tool(self) -> None:
        """When prompt.confirm() returns True, tool is executed."""
        prompt = _make_prompt(confirm_return=True)
        config = _make_config(prompt=prompt)
        tool = _make_tool()
        executor = MagicMock()

        result = execute_tool_passes(tool, MagicMock(), config, executor)

        assert result is not None
        executor.run.assert_called_once()

    def test_no_remaining_tools_skips_approve_all(self) -> None:
        """With remaining_tools=0, approve_all_remaining() is never called."""
        prompt = _make_prompt()
        config = _make_config(prompt=prompt)
        tool = _make_tool()

        execute_tool_passes(tool, MagicMock(), config, MagicMock(), remaining_tools=0)

        prompt.approve_all_remaining.assert_not_called()

    def test_remaining_tools_triggers_approve_all(self) -> None:
        """With remaining_tools>0, approve_all_remaining() is called."""
        prompt = _make_prompt()
        config = _make_config(prompt=prompt)
        tool = _make_tool()

        execute_tool_passes(tool, MagicMock(), config, MagicMock(), remaining_tools=2)

        prompt.approve_all_remaining.assert_called_once_with()

    def test_confirm_called_with_tool_name(self) -> None:
        """confirm() is called with the tool name in the message."""
        prompt = _make_prompt()
        config = _make_config(prompt=prompt)
        tool = _make_tool(name="semgrep")

        execute_tool_passes(tool, MagicMock(), config, MagicMock())

        prompt.confirm.assert_called_once()
        question = prompt.confirm.call_args[0][0]
        assert "semgrep" in question

    def test_decline_with_remaining_skips_approve_all(self) -> None:
        """When confirm() is False, approve_all_remaining() is not called."""
        prompt = _make_prompt(confirm_return=False)
        config = _make_config(prompt=prompt)
        tool = _make_tool()

        execute_tool_passes(tool, MagicMock(), config, MagicMock(), remaining_tools=3)

        prompt.approve_all_remaining.assert_not_called()


class TestExecuteToolPassesSkip:
    def test_empty_pass_list_returns_none(self) -> None:
        """Empty pass list signals skip; execute_tool_passes returns None."""
        config = _make_config()
        tool = _make_tool()
        tool.build_execution_passes.return_value = []
        executor = MagicMock()

        result = execute_tool_passes(tool, MagicMock(), config, executor)

        assert result is None
        executor.run.assert_not_called()


class TestExecuteToolPassesOrchestratorIntegration:
    @pytest.mark.parametrize("remaining", [1, 2, 10])
    def test_approve_all_called_for_any_positive_remaining(
        self, remaining: int
    ) -> None:
        """approve_all_remaining() is invoked for any remaining_tools > 0."""
        prompt = _make_prompt()
        config = _make_config(prompt=prompt)
        tool = _make_tool()

        execute_tool_passes(
            tool, MagicMock(), config, MagicMock(), remaining_tools=remaining
        )

        prompt.approve_all_remaining.assert_called_once_with()
