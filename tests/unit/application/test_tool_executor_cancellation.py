"""Unit tests for ToolExecutor cancellation token wiring.

Real-subprocess cancellation is exercised in
``tests/integration/tools/test_subprocess_runner.py`` against the
SubprocessRunner adapter.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.locking.cancellation import CancellationToken
from application.ports.subprocess_runner import (
    SubprocessResult,
    SubprocessRunnerPort,
)
from application.tools.executor import ToolExecutor


class _StubRunner(SubprocessRunnerPort):
    def __init__(self) -> None:
        self.last_cancel_token: CancellationToken | None = None

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> SubprocessResult:
        del cmd, timeout, cwd, env
        self.last_cancel_token = cancel_token
        return SubprocessResult(returncode=0, stdout="", stderr="")


@pytest.fixture()
def executor(tmp_path: Path) -> ToolExecutor:
    return ToolExecutor(
        project_name="test",
        base_path=tmp_path,
        prompt=MagicMock(),
        subprocess_runner=_StubRunner(),
    )


def test_default_token_is_no_op(executor: ToolExecutor) -> None:
    """Without a token installed, behavior is unchanged."""
    assert executor._cancel_token.is_set() is False


def test_set_cancel_token_replaces_default(executor: ToolExecutor) -> None:
    token = CancellationToken()
    executor.set_cancel_token(token)
    assert executor._cancel_token is token


def test_token_is_threaded_through_to_runner(tmp_path: Path) -> None:
    """The installed token reaches the SubprocessRunner port on each call."""
    stub = _StubRunner()
    executor = ToolExecutor(
        project_name="test",
        base_path=tmp_path,
        prompt=MagicMock(),
        subprocess_runner=stub,
    )
    token = CancellationToken()
    executor.set_cancel_token(token)
    executor._spawn(["true"], timeout=5, cwd=None, env=None)
    assert stub.last_cancel_token is token
