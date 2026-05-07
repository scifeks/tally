"""Adapter contract tests for OpenCodeTriageAgent.

These pin the argv shape, cwd, stdin, env and error-translation behavior of
the OpenCode adapter. They do not invoke the real ``opencode`` binary;
``subprocess.run`` is patched so the command shape can be inspected and
exceptions injected.
"""
# ruff: noqa: E402, I001

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.agents.opencode_triage_agent import OpenCodeTriageAgent  # noqa: E402

pytestmark = pytest.mark.integration


def _ok_completed(*, stdout: str = "", stderr: str = "") -> MagicMock:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = stdout
    completed.stderr = stderr
    return completed


def test_invokes_opencode_binary(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "opencode"


def test_run_subcommand_present(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert cmd[1] == "run"


def test_dir_flag_present_with_cwd(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    idx = cmd.index("--dir")
    assert cmd[idx + 1] == str(tmp_path)


def test_json_format_flag_present(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    idx = cmd.index("--format")
    assert cmd[idx + 1] == "json"


def test_dangerously_skip_permissions_flag_present_in_subprocess(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_cwd_passed_to_subprocess(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert mock_run.call_args[1]["cwd"] == str(tmp_path)


def test_prompt_passed_via_stdin(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
        agent.run_session("hello finding 42", timeout_seconds=60, cwd=tmp_path)
    assert mock_run.call_args[1]["input"] == "hello finding 42"


def test_prepared_session_sets_opencode_config_env(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()

    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        with patch("subprocess.run", return_value=_ok_completed()) as mock_run:
            agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)

    env = mock_run.call_args[1]["env"]
    assert env["OPENCODE_CONFIG"].endswith("opencode.json")


def test_success_when_returncode_zero(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed()):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is True
    assert result.returncode == 0
    assert result.error is None


def test_failure_when_returncode_nonzero(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 2
    completed.stdout = ""
    completed.stderr = "boom"
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=completed):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is False
    assert result.returncode == 2
    assert result.stderr == "boom"


def test_stdout_is_captured_for_json_diagnostics(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_ok_completed(stdout='{"ok":true}')):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.stderr == '{"ok":true}'


def test_timeout_translated_to_failed_result(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    timeout = subprocess.TimeoutExpired(cmd=["opencode"], timeout=60)
    with patch("subprocess.run", side_effect=timeout):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is False
    assert result.returncode == -1
    assert result.error is not None
    assert "60" in result.error


def test_unexpected_exception_translated_to_failed_result(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", side_effect=FileNotFoundError("no opencode")):
        result = agent.run_session("prompt", timeout_seconds=60, cwd=tmp_path)
    assert result.success is False
    assert result.returncode == -1
    assert result.error == "no opencode"
