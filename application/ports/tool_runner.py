"""Transport-agnostic tool runner port.

Decouples the executor from subprocess mechanics so CLI and HTTP
tools share the same result type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class ToolRunOutput:
    """Transport-agnostic result of a tool execution."""

    returncode: int
    stdout: str
    stderr: str


@runtime_checkable
class CliToolRunnerPort(Protocol):
    """Run a CLI tool via subprocess and return a transport-agnostic
    result.

    Implementations wrap ``SubprocessRunnerPort``, translating
    ``SubprocessResult`` into ``ToolRunOutput``. Subprocess-specific
    exceptions propagate unchanged so the executor can handle them.
    """

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_token: CancellationToken | None = None,
        stdin_data: str | None = None,
    ) -> ToolRunOutput: ...
