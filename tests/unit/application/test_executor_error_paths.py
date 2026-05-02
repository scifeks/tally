"""Unit tests for ToolExecutor error paths and _needs_root
(application.tools.executor)."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import pytest

from application.locking.cancellation import CancellationToken
from application.ports.subprocess_runner import (
    SubprocessNotFound,
    SubprocessPermissionDenied,
    SubprocessResult,
    SubprocessRunnerPort,
    SubprocessTimeout,
)
from application.tools.executor import ToolExecutor, _needs_root
from domain.tools.base import ToolResult
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter


class _StubRunner(SubprocessRunnerPort):
    """SubprocessRunnerPort double driven by a side_effect or canned result."""

    def __init__(
        self,
        *,
        result: SubprocessResult | None = None,
        side_effect: BaseException | None = None,
    ) -> None:
        self._result = result
        self._side_effect = side_effect
        self.calls: list[list[str]] = []

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> SubprocessResult:
        self.calls.append(cmd)
        if self._side_effect is not None:
            raise self._side_effect
        assert self._result is not None
        return self._result


@pytest.fixture()
def runner() -> _StubRunner:
    return _StubRunner()


@pytest.fixture()
def executor(tmp_path: Path, runner: _StubRunner) -> ToolExecutor:
    return ToolExecutor(
        "test-project", tmp_path, NoApprovalPromptAdapter(), subprocess_runner=runner
    )


class TestExecutorErrorPaths:
    # _needs_root

    def test_needs_root_true_for_requires_root_privileges(self) -> None:
        assert _needs_root("Error: requires root privileges to proceed") is True

    def test_needs_root_true_is_case_insensitive(self) -> None:
        assert _needs_root("OPERATION NOT PERMITTED") is True

    def test_needs_root_true_for_quitting(self) -> None:
        assert _needs_root("quitting!") is True

    def test_needs_root_false_for_clean_stderr(self) -> None:
        assert _needs_root("exit status 1: no such file") is False

    # _timeout_result

    def test_timeout_result_returns_failed_tool_result(
        self, executor: ToolExecutor
    ) -> None:
        result = executor._timeout_result(
            "mytool", "2024-01-01T00:00:00", perf_counter() - 1.0, 300
        )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.tool_name == "mytool"
        assert "300" in result.output

    def test_timeout_result_duration_is_nonnegative(
        self, executor: ToolExecutor
    ) -> None:
        result = executor._timeout_result(
            "mytool", "2024-01-01T00:00:00", perf_counter() - 1.0, 300
        )
        assert result.duration_seconds >= 0.0

    # _run_with_escalation

    def test_run_with_escalation_timeout_returns_tool_result(
        self, tmp_path: Path
    ) -> None:
        runner = _StubRunner(side_effect=SubprocessTimeout(["cmd"], 300))
        exec_ = ToolExecutor(
            "p", tmp_path, NoApprovalPromptAdapter(), subprocess_runner=runner
        )
        result = exec_._run_with_escalation(
            ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
        )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "timed out" in result.output.lower()

    def test_run_with_escalation_file_not_found_returns_tool_result(
        self, tmp_path: Path
    ) -> None:
        runner = _StubRunner(side_effect=SubprocessNotFound("cmd not found"))
        exec_ = ToolExecutor(
            "p", tmp_path, NoApprovalPromptAdapter(), subprocess_runner=runner
        )
        result = exec_._run_with_escalation(
            ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
        )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "not found" in result.output.lower()

    def test_run_with_escalation_permission_error_returns_tool_result(
        self, tmp_path: Path
    ) -> None:
        runner = _StubRunner(side_effect=SubprocessPermissionDenied("denied"))
        exec_ = ToolExecutor(
            "p", tmp_path, NoApprovalPromptAdapter(), subprocess_runner=runner
        )
        result = exec_._run_with_escalation(
            ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
        )
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "denied" in result.output.lower()

    def test_run_with_escalation_success_returns_named_tuple_not_tool_result(
        self, tmp_path: Path
    ) -> None:
        runner = _StubRunner(
            result=SubprocessResult(returncode=0, stdout="ok", stderr="")
        )
        exec_ = ToolExecutor(
            "p", tmp_path, NoApprovalPromptAdapter(), subprocess_runner=runner
        )
        result = exec_._run_with_escalation(
            ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
        )
        assert not isinstance(result, ToolResult)
        assert hasattr(result, "proc")


class _RecordingReporter:
    """Test double that records every report() call."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def report(self, message: str) -> None:
        self.messages.append(message)


class TestExecutorReporterWiring:
    """Cover the ProgressReporter port hook in ToolExecutor."""

    def test_default_reporter_is_silent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        runner = _StubRunner(side_effect=SubprocessNotFound("nope"))
        executor = ToolExecutor(
            "p", tmp_path, NoApprovalPromptAdapter(), subprocess_runner=runner
        )
        executor._run_with_escalation(
            ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
        )
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_injected_reporter_receives_failure_message(self, tmp_path: Path) -> None:
        reporter = _RecordingReporter()
        runner = _StubRunner(side_effect=SubprocessNotFound("nope"))
        executor = ToolExecutor(
            "p",
            tmp_path,
            NoApprovalPromptAdapter(),
            subprocess_runner=runner,
            reporter=reporter,
        )
        executor._run_with_escalation(
            ["cmd"], "mytool", "ts", 300, None, perf_counter(), False
        )
        assert reporter.messages == ["    ✗ Failed  (command not found)"]

    def test_timeout_routes_through_reporter(self, tmp_path: Path) -> None:
        reporter = _RecordingReporter()
        runner = _StubRunner()
        executor = ToolExecutor(
            "p",
            tmp_path,
            NoApprovalPromptAdapter(),
            subprocess_runner=runner,
            reporter=reporter,
        )
        executor._timeout_result("mytool", "ts", perf_counter() - 1.0, 300)
        assert reporter.messages == ["    ✗ Failed  (timeout after 300s)"]
