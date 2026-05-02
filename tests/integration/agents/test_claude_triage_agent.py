"""Adapter contract tests for ClaudeTriageAgent.

These pin the argv shape, cwd, stdin, and error-translation behavior of
the Claude Code adapter. They do not invoke the real ``claude`` binary;
``subprocess.run`` is patched so the command shape can be inspected and
exceptions can be injected.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.agents.claude_triage_agent import (  # noqa: E402
    ClaudeTriageAgent,
)

pytestmark = pytest.mark.integration


def _ok_completed() -> MagicMock:
    completed = MagicMock()
    completed.returncode = 0
    completed.stderr = ""
    return completed


def test_invokes_claude_binary(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"


def test_print_flag_present(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "--print" in cmd


def test_skip_permissions_flag_present(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_disallowed_tools_value_pinned(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    idx = cmd.index("--disallowedTools")
    assert cmd[idx + 1] == "Bash,Write,Edit,MultiEdit,WebFetch,WebSearch"


def test_cwd_passed_to_subprocess(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert mock_run.call_args[1]["cwd"] == str(tmp_path)


def test_prompt_passed_via_stdin(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("hello finding 42", timeout_seconds=60, cwd=tmp_path)
    assert mock_run.call_args[1]["input"] == "hello finding 42"


def test_success_when_returncode_zero(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is True
    assert result.returncode == 0
    assert result.error is None


def test_failure_when_returncode_nonzero(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 2
    completed.stderr = "boom"
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", return_value=completed):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is False
    assert result.returncode == 2
    assert result.stderr == "boom"


def test_timeout_translated_to_failed_result(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    timeout = subprocess.TimeoutExpired(cmd=["claude"], timeout=60)
    with patch("subprocess.run", side_effect=timeout):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is False
    assert result.returncode == -1
    assert result.error is not None
    assert "60" in result.error


def test_unexpected_exception_translated_to_failed_result(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent()
    with patch("subprocess.run", side_effect=FileNotFoundError("no claude")):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is False
    assert result.returncode == -1
    assert result.error == "no claude"
