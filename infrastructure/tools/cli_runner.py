"""CLI tool runner: wraps SubprocessRunner behind the
transport-agnostic CliToolRunnerPort contract."""

from __future__ import annotations

from application.locking.cancellation import CancellationToken
from application.ports.subprocess_runner import SubprocessRunnerPort
from application.ports.tool_runner import CliToolRunnerPort, ToolRunOutput


class CliToolRunner(CliToolRunnerPort):
    """Adapter that delegates to a SubprocessRunnerPort and
    translates SubprocessResult into ToolRunOutput.

    Subprocess-specific exceptions propagate unchanged so callers
    can handle timeout, not-found, and permission errors.
    """

    def __init__(self, subprocess_runner: SubprocessRunnerPort) -> None:
        self._subprocess_runner = subprocess_runner

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
        result = self._subprocess_runner.run(
            cmd,
            timeout=timeout,
            cwd=cwd,
            env=env,
            cancel_token=cancel_token,
            stdin_data=stdin_data,
        )
        return ToolRunOutput(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
