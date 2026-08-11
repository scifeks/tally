"""Adapter contract tests for ClaudeTriageAgent.

Pin the relay command shape, stdin framing, and error
translation of the Claude Code adapter running inside
Docker. ``subprocess.Popen`` is patched so the command
shape can be inspected and exceptions can be injected.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.verdict import VerdictParseError
from infrastructure.agents.claude_triage_agent import (
    ClaudeTriageAgent,
)

pytestmark = pytest.mark.integration

_COMPOSE = Path("/tmp/docker-compose.yml")
_MODEL = "claude-opus-4-5"


def _make_agent() -> ClaudeTriageAgent:
    return ClaudeTriageAgent(model=_MODEL, compose_path=_COMPOSE)


def _relay_response(stdout: str, *, rc: int = 0, stderr: str = "") -> str:
    b64_out = base64.b64encode(stdout.encode()).decode()
    b64_err = base64.b64encode(stderr.encode()).decode()
    return json.dumps({"rc": rc, "out": b64_out, "err": b64_err})


def _mock_relay(response_line: str) -> MagicMock:
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdout.readline.return_value = response_line + "\n"
    proc.stdin = MagicMock()
    return proc


def _ok_verdict(finding_id: int = 1) -> str:
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
    return json.dumps(verdict_obj)


def test_relay_starts_docker_compose(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert cmd[0] == "docker"
    assert cmd[1] == "compose"


def test_compose_file_passed(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert "-f" in cmd
    idx = cmd.index("-f")
    assert cmd[idx + 1] == str(_COMPOSE)


def test_print_flag_present(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert "--print" in cmd


def test_skip_permissions_flag_present(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_model_flag_matches_config(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    idx = cmd.index("--model")
    assert cmd[idx + 1] == _MODEL


def test_prompt_sent_as_base64_via_relay(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    response = _relay_response(_ok_verdict())
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            agent.run_triage(
                "hello finding 42",
                finding_id=1,
                timeout_seconds=60,
                cwd=tmp_path,
            )
    written = mock_proc.stdin.write.call_args[0][0]
    lines = written.strip().split("\n")
    decoded = base64.b64decode(lines[1]).decode()
    assert decoded == "hello finding 42"


def test_success_returns_verdict(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    response = _relay_response(_ok_verdict())
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            result = agent.run_triage(
                "prompt",
                finding_id=1,
                timeout_seconds=60,
                cwd=tmp_path,
            )
    assert result.finding_id == 1
    assert result.confidence == "confirmed"


def test_failure_when_returncode_nonzero(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    response = _relay_response("", rc=2, stderr="boom")
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            with pytest.raises(
                VerdictParseError,
                match="exited with code 2",
            ):
                agent.run_triage(
                    "prompt",
                    finding_id=1,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_timeout_raises_timeout_expired(
    tmp_path: Path,
) -> None:
    agent = _make_agent()
    response = _relay_response("", rc=124)
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="p",
            run_id=1,
            app_root=tmp_path,
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                agent.run_triage(
                    "prompt",
                    finding_id=1,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )
