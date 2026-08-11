"""Unit tests for OpenCodeTriageAgent.

Pin the relay startup, framing protocol, NDJSON event stream
parsing, and error translation of the OpenCode adapter.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.verdict import (
    Verdict,
    VerdictParseError,
)
from infrastructure.agents.opencode_triage_agent import (
    OpenCodeTriageAgent,
)

_FINDING_ID = 42
_COMPOSE_PATH = Path("/app/docker/triage-agent/docker-compose.yaml")


def _agent() -> OpenCodeTriageAgent:
    return OpenCodeTriageAgent(compose_path=_COMPOSE_PATH)


def _valid_verdict(**overrides: object) -> dict:
    base: dict = {
        "finding_id": _FINDING_ID,
        "confidence": "confirmed",
        "finding_type": "vulnerability",
        "severity": "high",
        "reasoning": "User input reaches the sink.",
        "remediation": "Use parameterized queries.",
        "attack_vector": "POST /login password",
        "call_stack": ["app.php:10 handle"],
        "access_required": "none",
        "exploitation_complexity": "low",
        "user_interaction": "none",
    }
    base.update(overrides)
    return base


def _opencode_event_stream(verdict_text: str) -> str:
    events = [
        json.dumps(
            {
                "type": "step_start",
                "timestamp": 1000,
                "sessionID": "ses_test",
                "part": {"type": "step-start"},
            }
        ),
        json.dumps(
            {
                "type": "text",
                "timestamp": 1001,
                "sessionID": "ses_test",
                "part": {
                    "type": "text",
                    "text": verdict_text,
                },
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "timestamp": 1002,
                "sessionID": "ses_test",
                "part": {"type": "step-finish"},
            }
        ),
    ]
    return "\n".join(events) + "\n"


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


# -- session prep / relay startup -------------------------


def test_prepare_session_yields_cwd(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent(compose_path=tmp_path / "compose.yaml")
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="proj",
            run_id=1,
            app_root=tmp_path,
        ) as session:
            assert session.cwd == tmp_path


def test_prepare_session_starts_relay(
    tmp_path: Path,
) -> None:
    agent = _agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="proj",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert "docker" in cmd
    assert "compose" in cmd
    assert "triage-relay" in cmd
    assert "opencode" in cmd
    assert "run" in cmd


def test_relay_command_includes_format_json(
    tmp_path: Path,
) -> None:
    agent = _agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="proj",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert "--format" in cmd
    assert "json" in cmd
    assert "--dir" in cmd
    assert "/workspace" in cmd


def test_relay_command_includes_config_env(
    tmp_path: Path,
) -> None:
    agent = _agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
        with agent.prepare_session(
            project="proj",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    cmd = popen_mock.call_args[0][0]
    assert "-e" in cmd
    assert "OPENCODE_CONFIG=/etc/opencode/opencode.json" in cmd


def test_prepare_session_terminates_relay(
    tmp_path: Path,
) -> None:
    agent = _agent()
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="proj",
            run_id=1,
            app_root=tmp_path,
        ):
            pass
    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called_once()


# -- happy path -------------------------------------------


def test_happy_path_returns_verdict(
    tmp_path: Path,
) -> None:
    agent = _agent()
    stdout = _opencode_event_stream(json.dumps(_valid_verdict()))
    response = _relay_response(stdout)
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            verdict = agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )
    assert isinstance(verdict, Verdict)
    assert verdict.finding_id == _FINDING_ID
    assert verdict.confidence == "confirmed"
    assert verdict.severity == "high"


def test_prompt_sent_as_base64(
    tmp_path: Path,
) -> None:
    agent = _agent()
    stdout = _opencode_event_stream(json.dumps(_valid_verdict()))
    response = _relay_response(stdout)
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            agent.run_triage(
                "hello finding 42",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )
    written = mock_proc.stdin.write.call_args[0][0]
    lines = written.strip().split("\n")
    assert lines[0] == "60"
    decoded = base64.b64decode(lines[1]).decode()
    assert decoded == "hello finding 42"


def test_multiple_text_events_concatenated(
    tmp_path: Path,
) -> None:
    verdict = _valid_verdict()
    verdict_json = json.dumps(verdict)
    half = len(verdict_json) // 2
    part_a = verdict_json[:half]
    part_b = verdict_json[half:]
    events = [
        json.dumps(
            {
                "type": "text",
                "timestamp": 1,
                "sessionID": "s",
                "part": {"type": "text", "text": part_a},
            }
        ),
        json.dumps(
            {
                "type": "text",
                "timestamp": 2,
                "sessionID": "s",
                "part": {"type": "text", "text": part_b},
            }
        ),
    ]
    stdout = "\n".join(events) + "\n"
    response = _relay_response(stdout)
    mock_proc = _mock_relay(response)
    agent = _agent()
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            result = agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )
    assert isinstance(result, Verdict)
    assert result.finding_id == _FINDING_ID


# -- error handling ---------------------------------------


def test_nonzero_exit_raises(tmp_path: Path) -> None:
    agent = _agent()
    response = _relay_response("", rc=1, stderr="bad")
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with pytest.raises(
                VerdictParseError,
                match="exited with code 1",
            ):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_timeout_exit_code_raises_timeout(
    tmp_path: Path,
) -> None:
    agent = _agent()
    response = _relay_response("", rc=124)
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with pytest.raises(subprocess.TimeoutExpired):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_relay_death_raises(tmp_path: Path) -> None:
    agent = _agent()
    mock_proc = _mock_relay("")
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            mock_proc.poll.return_value = 1
            with pytest.raises(RuntimeError, match="exited"):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_empty_stdout_raises(
    tmp_path: Path,
) -> None:
    agent = _agent()
    response = _relay_response("")
    mock_proc = _mock_relay(response)
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with pytest.raises(
                VerdictParseError,
                match="empty stdout",
            ):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_no_text_events_raises(
    tmp_path: Path,
) -> None:
    non_text = "\n".join(
        [
            json.dumps({"type": "step_start", "part": {}}),
            json.dumps({"type": "step_finish", "part": {}}),
        ]
    )
    response = _relay_response(non_text)
    mock_proc = _mock_relay(response)
    agent = _agent()
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with pytest.raises(
                VerdictParseError,
                match="no text events",
            ):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_finding_id_mismatch_raises(
    tmp_path: Path,
) -> None:
    stdout = _opencode_event_stream(json.dumps(_valid_verdict(finding_id=99)))
    response = _relay_response(stdout)
    mock_proc = _mock_relay(response)
    agent = _agent()
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with pytest.raises(
                VerdictParseError,
                match="finding_id mismatch",
            ):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )


def test_missing_verdict_field_raises(
    tmp_path: Path,
) -> None:
    incomplete = {
        "finding_id": _FINDING_ID,
        "confidence": "confirmed",
    }
    stdout = _opencode_event_stream(json.dumps(incomplete))
    response = _relay_response(stdout)
    mock_proc = _mock_relay(response)
    agent = _agent()
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with pytest.raises(
                VerdictParseError,
                match="missing fields",
            ):
                agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )
