"""Unit tests for tool execution dispatch: port contract,
CLI runner, HTTP runner, and transport routing."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.locking.cancellation import CancellationToken
from application.ports.subprocess_runner import (
    SubprocessCancelled,
    SubprocessNotFound,
    SubprocessResult,
    SubprocessRunnerPort,
    SubprocessTimeout,
)
from application.ports.tool_runner import (
    CliToolRunnerPort,
    ToolRunOutput,
)
from application.tools.executor import ToolExecutor
from domain.tools.interface import TransportType


class TestToolRunOutput:
    def test_frozen_dataclass_fields(self) -> None:
        out = ToolRunOutput(returncode=0, stdout="ok", stderr="")
        assert out.returncode == 0
        assert out.stdout == "ok"
        assert out.stderr == ""

    def test_immutable(self) -> None:
        out = ToolRunOutput(returncode=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            out.returncode = 1  # type: ignore[misc]


class TestTransportType:
    def test_cli_value(self) -> None:
        assert TransportType.CLI.value == "cli"

    def test_http_value(self) -> None:
        assert TransportType.HTTP.value == "http"


class TestToolInterfaceTransportDefault:
    def test_default_transport_is_cli(self) -> None:
        from unittest.mock import MagicMock

        from domain.tools.interface import ToolInterface

        mock = MagicMock(spec=ToolInterface)
        mock.transport = ToolInterface.transport.fget(mock)  # type: ignore[union-attr]
        assert mock.transport == TransportType.CLI


class _StubSubprocessRunner(SubprocessRunnerPort):
    """Records calls and returns a canned result."""

    def __init__(
        self,
        *,
        result: SubprocessResult | None = None,
        side_effect: BaseException | None = None,
    ) -> None:
        self._result = result
        self._side_effect = side_effect
        self.calls: list[dict] = []

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_token: CancellationToken | None = None,
        stdin_data: str | None = None,
    ) -> SubprocessResult:
        self.calls.append(
            {
                "cmd": cmd,
                "timeout": timeout,
                "cwd": cwd,
                "env": env,
                "cancel_token": cancel_token,
                "stdin_data": stdin_data,
            }
        )
        if self._side_effect is not None:
            raise self._side_effect
        assert self._result is not None
        return self._result


class TestCliToolRunner:
    def test_satisfies_protocol(self) -> None:
        from infrastructure.tools.cli_runner import CliToolRunner

        stub = _StubSubprocessRunner(
            result=SubprocessResult(returncode=0, stdout="", stderr="")
        )
        runner = CliToolRunner(stub)
        assert isinstance(runner, CliToolRunnerPort)

    def test_delegates_to_subprocess_runner(self) -> None:
        from infrastructure.tools.cli_runner import CliToolRunner

        stub = _StubSubprocessRunner(
            result=SubprocessResult(returncode=0, stdout="out", stderr="err")
        )
        token = CancellationToken()
        runner = CliToolRunner(stub)
        runner.run(
            ["semgrep", "--json"],
            timeout=300,
            cwd="/repo",
            env={"PATH": "/bin"},
            cancel_token=token,
            stdin_data="input",
        )
        assert len(stub.calls) == 1
        call = stub.calls[0]
        assert call["cmd"] == ["semgrep", "--json"]
        assert call["timeout"] == 300
        assert call["cwd"] == "/repo"
        assert call["env"] == {"PATH": "/bin"}
        assert call["cancel_token"] is token
        assert call["stdin_data"] == "input"

    def test_translates_result_to_tool_run_output(self) -> None:
        from infrastructure.tools.cli_runner import CliToolRunner

        stub = _StubSubprocessRunner(
            result=SubprocessResult(returncode=42, stdout="findings", stderr="warn")
        )
        runner = CliToolRunner(stub)
        out = runner.run(["tool"], timeout=60)
        assert isinstance(out, ToolRunOutput)
        assert out.returncode == 42
        assert out.stdout == "findings"
        assert out.stderr == "warn"

    def test_subprocess_timeout_propagates(self) -> None:
        from infrastructure.tools.cli_runner import CliToolRunner

        stub = _StubSubprocessRunner(side_effect=SubprocessTimeout(["cmd"], 300))
        runner = CliToolRunner(stub)
        with pytest.raises(SubprocessTimeout):
            runner.run(["cmd"], timeout=300)

    def test_subprocess_not_found_propagates(self) -> None:
        from infrastructure.tools.cli_runner import CliToolRunner

        stub = _StubSubprocessRunner(side_effect=SubprocessNotFound("nope"))
        runner = CliToolRunner(stub)
        with pytest.raises(SubprocessNotFound):
            runner.run(["cmd"], timeout=300)

    def test_subprocess_cancelled_propagates(self) -> None:
        from infrastructure.tools.cli_runner import CliToolRunner

        stub = _StubSubprocessRunner(side_effect=SubprocessCancelled())
        runner = CliToolRunner(stub)
        with pytest.raises(SubprocessCancelled):
            runner.run(["cmd"], timeout=300)


class TestHttpToolRunner:
    def test_importable(self) -> None:
        from infrastructure.tools.http_runner import HttpToolRunner

        runner = HttpToolRunner()
        assert runner is not None

    def test_execute_burp_without_client_returns_failure(self) -> None:
        from infrastructure.tools.http_runner import HttpToolRunner

        runner = HttpToolRunner()
        result = runner.execute_burp(
            config=MagicMock(),
            cancel_token=None,
            event_sink=None,
            run_id=0,
            project_id=None,
        )
        assert result.success is False
        assert result.tool_name == "burp"
        assert result.output == "Burp client not configured"


class _StubCliRunner(CliToolRunnerPort):
    """CliToolRunnerPort stub for executor tests."""

    def __init__(
        self,
        *,
        result: ToolRunOutput | None = None,
        side_effect: BaseException | None = None,
    ) -> None:
        self._result = result or ToolRunOutput(returncode=0, stdout="", stderr="")
        self._side_effect = side_effect
        self.calls: list[dict] = []

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_token: CancellationToken | None = None,
        stdin_data: str | None = None,
    ) -> ToolRunOutput:
        self.calls.append(
            {
                "cmd": cmd,
                "timeout": timeout,
                "cwd": cwd,
                "env": env,
                "cancel_token": cancel_token,
                "stdin_data": stdin_data,
            }
        )
        if self._side_effect is not None:
            raise self._side_effect
        return self._result


class TestExecutorDispatch:
    def test_spawn_delegates_to_cli_runner(self, tmp_path) -> None:
        stub = _StubCliRunner(
            result=ToolRunOutput(returncode=0, stdout="ok", stderr="")
        )
        executor = ToolExecutor(
            project_name="test",
            base_path=tmp_path,
            prompt=MagicMock(),
            cli_tool_runner=stub,
        )
        out = executor._spawn(
            ["semgrep", "--json"],
            timeout=300,
            cwd="/repo",
            env=None,
        )
        assert isinstance(out, ToolRunOutput)
        assert out.stdout == "ok"
        assert len(stub.calls) == 1

    def test_spawn_threads_cancel_token(self, tmp_path) -> None:
        stub = _StubCliRunner()
        executor = ToolExecutor(
            project_name="test",
            base_path=tmp_path,
            prompt=MagicMock(),
            cli_tool_runner=stub,
        )
        token = CancellationToken()
        executor.set_cancel_token(token)
        executor._spawn(["true"], timeout=5, cwd=None, env=None)
        assert stub.calls[0]["cancel_token"] is token

    def test_spawn_translates_cancellation(self, tmp_path) -> None:
        from application.tools.executor import ToolCancelled

        stub = _StubCliRunner(side_effect=SubprocessCancelled())
        executor = ToolExecutor(
            project_name="test",
            base_path=tmp_path,
            prompt=MagicMock(),
            cli_tool_runner=stub,
        )
        with pytest.raises(ToolCancelled):
            executor._spawn(["cmd"], timeout=5, cwd=None, env=None)

    def test_spawn_returns_tool_run_output_not_subprocess_result(
        self, tmp_path
    ) -> None:
        stub = _StubCliRunner(
            result=ToolRunOutput(returncode=1, stdout="findings", stderr="warn")
        )
        executor = ToolExecutor(
            project_name="test",
            base_path=tmp_path,
            prompt=MagicMock(),
            cli_tool_runner=stub,
        )
        out = executor._spawn(["tool"], timeout=60, cwd=None, env=None)
        assert type(out) is ToolRunOutput
        assert out.returncode == 1
        assert out.stdout == "findings"
        assert out.stderr == "warn"
