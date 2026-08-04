"""Adapter contract tests for ClaudeTriageAgent.

These pin the argv shape, cwd, stdin, and error-translation behavior of
the Claude Code adapter running inside Docker. They do not invoke the
real ``claude`` binary; ``subprocess.run`` is patched so the command
shape can be inspected and exceptions can be injected.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.verdict import VerdictParseError  # noqa: E402
from infrastructure.agents.claude_triage_agent import (  # noqa: E402
    ClaudeTriageAgent,
)

pytestmark = pytest.mark.integration

_COMPOSE = Path("/tmp/docker-compose.yml")
_MODEL = "claude-opus-4-5"


def _make_agent() -> ClaudeTriageAgent:
    return ClaudeTriageAgent(model=_MODEL, compose_path=_COMPOSE)


def _ok_verdict(finding_id: int = 1) -> MagicMock:
    verdict_obj = {
        "finding_id": finding_id,
        "confidence": "confirmed",
        "finding_type": "vulnerability",
        "severity": "high",
        "reasoning": "test",
        "remediation": "fix",
        "attack_vector": "network",
        "access_required": "none",
        "exploitation_complexity": "low",
        "user_interaction": "none",
        "call_stack": [],
    }
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = json.dumps(verdict_obj)
    completed.stderr = ""
    return completed


def test_invokes_docker_compose(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()) as mock_run:
        agent.run_triage(
            "prompt",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "docker"
    assert cmd[1] == "compose"


def test_compose_file_passed(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()) as mock_run:
        agent.run_triage(
            "prompt",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = mock_run.call_args[0][0]
    assert "-f" in cmd
    idx = cmd.index("-f")
    assert cmd[idx + 1] == str(_COMPOSE)


def test_print_flag_present(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()) as mock_run:
        agent.run_triage(
            "prompt",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = mock_run.call_args[0][0]
    assert "--print" in cmd


def test_skip_permissions_flag_present(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()) as mock_run:
        agent.run_triage(
            "prompt",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = mock_run.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_model_flag_matches_config(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()) as mock_run:
        agent.run_triage(
            "prompt",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = mock_run.call_args[0][0]
    idx = cmd.index("--model")
    assert cmd[idx + 1] == _MODEL


def test_prompt_passed_via_stdin(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()) as mock_run:
        agent.run_triage(
            "hello finding 42",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert mock_run.call_args[1]["input"] == "hello finding 42"


def test_success_returns_verdict(tmp_path: Path) -> None:
    agent = _make_agent()
    with patch("subprocess.run", return_value=_ok_verdict()):
        result = agent.run_triage(
            "prompt",
            finding_id=1,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert result.finding_id == 1
    assert result.confidence == "confirmed"


def test_failure_when_returncode_nonzero(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 2
    completed.stderr = "boom"
    agent = _make_agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="exited with code 2"):
            agent.run_triage(
                "prompt",
                finding_id=1,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_timeout_raises_verdict_parse_error(tmp_path: Path) -> None:
    agent = _make_agent()
    timeout = subprocess.TimeoutExpired(cmd=["docker"], timeout=60)
    with patch("subprocess.run", side_effect=timeout):
        with pytest.raises(subprocess.TimeoutExpired):
            agent.run_triage(
                "prompt",
                finding_id=1,
                timeout_seconds=60,
                cwd=tmp_path,
            )
