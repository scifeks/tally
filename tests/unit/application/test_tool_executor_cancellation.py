"""Unit tests for Phase 5.2 ToolExecutor cancellation."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.locking.cancellation import CancellationToken
from application.tools.executor import ToolCancelled, ToolExecutor


@pytest.fixture()
def executor(tmp_path: Path) -> ToolExecutor:
    return ToolExecutor(
        project_name="test",
        base_path=tmp_path,
        prompt=MagicMock(),
    )


def test_default_token_is_no_op(executor: ToolExecutor) -> None:
    """Without a token installed, behavior is unchanged."""
    assert executor._cancel_token.is_set() is False


def test_set_cancel_token_replaces_default(executor: ToolExecutor) -> None:
    token = CancellationToken()
    executor.set_cancel_token(token)
    assert executor._cancel_token is token


def test_run_subprocess_aborts_on_cancellation(
    executor: ToolExecutor,
) -> None:
    """Cancellation set during a long sleep raises ToolCancelled."""
    token = CancellationToken()
    executor.set_cancel_token(token)

    # set the token shortly after subprocess starts
    threading.Timer(0.2, token.set).start()

    with pytest.raises(ToolCancelled):
        executor._run_subprocess(
            ["sleep", "30"],
            timeout=10,
            cwd=None,
        )


def test_run_subprocess_runs_normally_when_not_cancelled(
    executor: ToolExecutor,
) -> None:
    """Without cancellation the subprocess completes and returns normally."""
    result = executor._run_subprocess(
        ["true"],
        timeout=5,
        cwd=None,
    )
    assert result.returncode == 0
