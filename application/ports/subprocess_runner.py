"""SubprocessRunner port: spawn-and-wait seam over child processes.

Adapters:
  infrastructure/tools/runner.py::SubprocessRunner

Owns process-group spawn, cancellation polling, signal escalation,
and timeout enforcement so application services never touch
``subprocess`` / ``os`` / ``signal`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str


class SubprocessError(RuntimeError):
    """Base for SubprocessRunnerPort failures."""


class SubprocessCancelled(SubprocessError):
    """Raised when the cancel token was observed set during a wait."""


class SubprocessTimeout(SubprocessError):
    """Raised when the subprocess exceeded its deadline."""

    def __init__(self, cmd: list[str], timeout: int) -> None:
        super().__init__(f"command {cmd[0]!r} exceeded {timeout}s")
        self.cmd = cmd
        self.timeout = timeout


class SubprocessNotFound(SubprocessError):
    """Raised when the binary was not on PATH."""


class SubprocessPermissionDenied(SubprocessError):
    """Raised when the OS denied execution."""


@runtime_checkable
class SubprocessRunnerPort(Protocol):
    """Run a single subprocess with cancellation + timeout enforcement.

    Implementations spawn the command in its own process group, poll the
    optional ``cancel_token`` while waiting, and translate stdlib exceptions
    into the port-defined error types above. The application service decides
    what each error means (e.g. sudo escalation on permission denial).
    """

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> SubprocessResult: ...
