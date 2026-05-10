"""Adapter contract tests for SubprocessRunner against real binaries.

These exercise the runner end-to-end against ``true``, ``false``, ``sleep``,
and a missing binary. Cancellation is exercised in a background thread so
the cancel-token-while-running path is covered without leaking children.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.locking.cancellation import CancellationToken  # noqa: E402
from application.ports.subprocess_runner import (  # noqa: E402
    SubprocessCancelled,
    SubprocessNotFound,
    SubprocessTimeout,
)
from infrastructure.tools.runner import SubprocessRunner  # noqa: E402

pytestmark = pytest.mark.integration


def test_returns_result_on_normal_exit() -> None:
    result = SubprocessRunner().run(["true"], timeout=5)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_returns_nonzero_on_failure() -> None:
    result = SubprocessRunner().run(["false"], timeout=5)
    assert result.returncode != 0


def test_captures_stdout() -> None:
    result = SubprocessRunner().run(["sh", "-c", "printf hello"], timeout=5)
    assert result.stdout == "hello"


def test_passes_env() -> None:
    result = SubprocessRunner().run(
        ["sh", "-c", "printf $MY_VAR"],
        timeout=5,
        env={"MY_VAR": "from-env"},
    )
    assert result.stdout == "from-env"


def test_passes_cwd(tmp_path: Path) -> None:
    result = SubprocessRunner().run(["pwd"], timeout=5, cwd=str(tmp_path))
    assert result.stdout.strip() == str(tmp_path)


def test_raises_not_found_for_missing_binary() -> None:
    with pytest.raises(SubprocessNotFound):
        SubprocessRunner().run(["/nonexistent/binary/xyz"], timeout=5)


def test_raises_timeout_when_deadline_exceeded() -> None:
    start = time.monotonic()
    with pytest.raises(SubprocessTimeout):
        SubprocessRunner().run(["sleep", "30"], timeout=1)
    # The runner uses integer-second timeout but polls every 0.5s, so the
    # actual cleanup may take slightly over 1s. Cap generously.
    assert time.monotonic() - start < 5


def test_raises_cancelled_when_token_set_mid_run() -> None:
    token = CancellationToken()

    def _trip() -> None:
        time.sleep(0.5)
        token.set()

    threading.Thread(target=_trip, daemon=True).start()

    with pytest.raises(SubprocessCancelled):
        SubprocessRunner().run(["sleep", "30"], timeout=10, cancel_token=token)


def test_cancellation_kills_process_group() -> None:
    """A canceled subprocess must not leave its process group running."""
    token = CancellationToken()

    runner = SubprocessRunner()
    captured_pid: dict[str, int] = {}

    def _trip() -> None:
        # Wait for the child to spawn before cancelling.
        for _ in range(50):
            time.sleep(0.05)
            if captured_pid:
                break
        token.set()

    threading.Thread(target=_trip, daemon=True).start()

    # Wrap Popen so we can record the pid before the cancel arrives.
    import subprocess as _sp

    real_popen = _sp.Popen

    def spy_popen(*args: object, **kwargs: object) -> _sp.Popen:
        proc = real_popen(*args, **kwargs)  # type: ignore[arg-type]
        captured_pid["pid"] = proc.pid
        return proc

    _sp.Popen = spy_popen  # type: ignore[assignment]
    try:
        with pytest.raises(SubprocessCancelled):
            runner.run(["sleep", "30"], timeout=10, cancel_token=token)
    finally:
        _sp.Popen = real_popen  # type: ignore[assignment]

    pid = captured_pid["pid"]
    # If the process group is still alive, signal 0 succeeds; if it's gone,
    # ProcessLookupError is raised.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.killpg(os.getpgid(pid), 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.1)
    pytest.fail("process group still alive after cancellation grace period")


def test_no_cancel_token_runs_to_completion() -> None:
    """Without a token, the runner waits for normal exit."""
    result = SubprocessRunner().run(["sh", "-c", "exit 7"], timeout=5)
    assert result.returncode == 7


def test_token_already_set_aborts_immediately() -> None:
    token = CancellationToken()
    token.set()
    with pytest.raises(SubprocessCancelled):
        SubprocessRunner().run(["sleep", "30"], timeout=10, cancel_token=token)
