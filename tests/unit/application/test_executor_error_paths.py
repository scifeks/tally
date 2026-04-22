"""Unit tests for ToolExecutor error paths and _needs_root
(application.tools.executor)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import pytest

from application.tools.executor import ToolExecutor, _needs_root
from domain.tools.base import ToolResult
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter


@pytest.fixture()
def executor(tmp_path: Path) -> ToolExecutor:
    return ToolExecutor("test-project", tmp_path, NoApprovalPromptAdapter())


class TestExecutorErrorPaths:
    # ------------------------------------------------------------------
    # _needs_root
    # ------------------------------------------------------------------

    def test_needs_root_true_for_requires_root_privileges(self) -> None:
        assert _needs_root("Error: requires root privileges to proceed") is True

    def test_needs_root_true_is_case_insensitive(self) -> None:
        assert _needs_root("OPERATION NOT PERMITTED") is True

    def test_needs_root_true_for_quitting(self) -> None:
        assert _needs_root("quitting!") is True

    def test_needs_root_false_for_clean_stderr(self) -> None:
        assert _needs_root("exit status 1: no such file") is False

    # ------------------------------------------------------------------
    # _timeout_result
    # ------------------------------------------------------------------

    def test_timeout_result_returns_failed_tool_result(self) -> None:
        result = ToolExecutor._timeout_result(
            "mytool", "2024-01-01T00:00:00", perf_counter() - 1.0, 300
        )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.tool_name == "mytool"
        assert "300" in result.output

    def test_timeout_result_duration_is_nonnegative(self) -> None:
        result = ToolExecutor._timeout_result(
            "mytool", "2024-01-01T00:00:00", perf_counter() - 1.0, 300
        )
        assert result.duration_seconds >= 0.0

    # ------------------------------------------------------------------
    # _run_with_escalation
    # ------------------------------------------------------------------

    def test_run_with_escalation_timeout_returns_tool_result(
        self, executor: ToolExecutor
    ) -> None:
        with patch.object(
            executor,
            "_run_subprocess",
            side_effect=subprocess.TimeoutExpired("cmd", 300),
        ):
            result = executor._run_with_escalation(
                ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
            )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "timed out" in result.output.lower()

    def test_run_with_escalation_file_not_found_returns_tool_result(
        self, executor: ToolExecutor
    ) -> None:
        with patch.object(
            executor,
            "_run_subprocess",
            side_effect=FileNotFoundError("cmd not found"),
        ):
            result = executor._run_with_escalation(
                ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
            )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "not found" in result.output.lower()

    def test_run_with_escalation_permission_error_returns_tool_result(
        self, executor: ToolExecutor
    ) -> None:
        with patch.object(
            executor,
            "_run_subprocess",
            side_effect=PermissionError("permission denied"),
        ):
            result = executor._run_with_escalation(
                ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
            )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "denied" in result.output.lower()

    def test_run_with_escalation_success_returns_named_tuple_not_tool_result(
        self, executor: ToolExecutor
    ) -> None:
        completed = subprocess.CompletedProcess(
            args=["cmd"], returncode=0, stdout="ok", stderr=""
        )
        with patch.object(executor, "_run_subprocess", return_value=completed):
            result = executor._run_with_escalation(
                ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
            )
        assert not isinstance(result, ToolResult)
        assert hasattr(result, "proc")
