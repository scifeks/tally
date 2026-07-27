"""SubprocessRunner adapter: concrete implementation of SubprocessRunnerPort.

Owns process-group spawn, cancel-token polling, signal escalation
(SIGTERM with grace period, SIGKILL on expiry), and timeout enforcement.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from time import perf_counter

from application.locking.cancellation import CancellationToken
from application.ports.subprocess_runner import (
    SubprocessCancelled,
    SubprocessNotFound,
    SubprocessPermissionDenied,
    SubprocessResult,
    SubprocessRunnerPort,
    SubprocessTimeout,
)

# Seconds between cancel-token checks while a subprocess is running.
_CANCEL_POLL_INTERVAL = 0.5
# Grace period after SIGTERM before SIGKILL when cancelling a subprocess.
_CANCEL_GRACE_SECONDS = 3.0


class SubprocessRunner(SubprocessRunnerPort):
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
        effective_env = {**os.environ, **env} if env else None
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                env=effective_env,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise SubprocessNotFound(str(exc)) from exc
        except PermissionError as exc:
            raise SubprocessPermissionDenied(str(exc)) from exc

        deadline = perf_counter() + timeout
        while True:
            if cancel_token is not None and cancel_token.is_set():
                _abort_proc_group(proc)
                raise SubprocessCancelled
            remaining = deadline - perf_counter()
            if remaining <= 0:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc.communicate()
                except Exception:
                    pass
                raise SubprocessTimeout(cmd, timeout)
            try:
                stdout, stderr = proc.communicate(
                    input=stdin_data, timeout=min(_CANCEL_POLL_INTERVAL, remaining)
                )
                stdin_data = None
                break
            except subprocess.TimeoutExpired:
                continue

        return SubprocessResult(
            returncode=proc.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
        )


def _abort_proc_group(proc: subprocess.Popen) -> None:
    """SIGTERM the process group, then SIGKILL after the grace period."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + _CANCEL_GRACE_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.communicate()
    except Exception:
        pass
