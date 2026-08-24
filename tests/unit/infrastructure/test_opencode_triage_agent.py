"""Unit tests for OpenCodeTriageAgent.

Pin the relay startup, framing protocol, verdict file-drop contract,
and error translation of the OpenCode adapter.
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


def _agent(tmp_path: Path) -> OpenCodeTriageAgent:
    return OpenCodeTriageAgent(
        compose_path=_COMPOSE_PATH,
        verdict_out_path=tmp_path / "verdict.json",
    )


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


def _write_verdict(tmp_path: Path, content: str) -> None:
    (tmp_path / "verdict.json").write_text(content)


def _relay_response(stdout: str = "", *, rc: int = 0, stderr: str = "") -> str:
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


def test_prepare_session_yields_cwd(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay('{"rc":0,"out":"","err":""}')
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(
            project="proj",
            run_id=1,
            app_root=tmp_path,
        ) as session:
            assert session.cwd == tmp_path


def test_prepare_session_starts_relay(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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


def test_relay_command_includes_format_json(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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


def test_relay_command_includes_config_env(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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


def test_prepare_session_terminates_relay(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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


def test_happy_path_returns_verdict(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay(_relay_response())

    def fake_dispatch(*_a: object, **_kw: object) -> None:
        _write_verdict(tmp_path, json.dumps(_valid_verdict()))

    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with patch.object(agent, "_dispatch_prompt", side_effect=fake_dispatch):
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


def test_prompt_sent_as_base64(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay(_relay_response())
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            # dispatch is real (writes to stdin), file is written inside it
            # so the real _load_verdict can read it back
            real_dispatch = agent._dispatch_prompt

            def dispatch_and_write(*a: object, **kw: object) -> None:
                real_dispatch(*a, **kw)  # type: ignore[arg-type]
                _write_verdict(tmp_path, json.dumps(_valid_verdict()))

            with patch.object(
                agent, "_dispatch_prompt", side_effect=dispatch_and_write
            ):
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


def test_clears_stale_verdict_before_dispatch(tmp_path: Path) -> None:
    """A verdict file left over from a prior attempt must not be reused."""
    agent = _agent(tmp_path)
    _write_verdict(tmp_path, json.dumps(_valid_verdict(finding_id=999)))
    mock_proc = _mock_relay(_relay_response())

    def fake_dispatch(*_a: object, **_kw: object) -> None:
        _write_verdict(tmp_path, json.dumps(_valid_verdict()))

    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with patch.object(agent, "_dispatch_prompt", side_effect=fake_dispatch):
                verdict = agent.run_triage(
                    "prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )
    assert verdict.finding_id == _FINDING_ID


def test_missing_file_triggers_retry_with_error_context(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay(_relay_response())
    dispatches: list[str] = []

    def fake_dispatch(prompt: str, **_kw: object) -> None:
        dispatches.append(prompt)
        # First attempt: model does not write the file (leaves it missing).
        # Retry: model writes a valid verdict.
        if len(dispatches) == 2:
            _write_verdict(tmp_path, json.dumps(_valid_verdict()))

    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with patch.object(agent, "_dispatch_prompt", side_effect=fake_dispatch):
                verdict = agent.run_triage(
                    "original prompt",
                    finding_id=_FINDING_ID,
                    timeout_seconds=60,
                    cwd=tmp_path,
                )
    assert verdict.finding_id == _FINDING_ID
    assert len(dispatches) == 2
    assert "Previous attempt failed" in dispatches[1]
    assert "/workspace/out/verdict.json" in dispatches[1]


def test_both_attempts_fail_raises(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay(_relay_response())
    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            # Neither dispatch writes the verdict file; both attempts fail.
            with patch.object(agent, "_dispatch_prompt"):
                with pytest.raises(VerdictParseError, match="verdict file not found"):
                    agent.run_triage(
                        "prompt",
                        finding_id=_FINDING_ID,
                        timeout_seconds=60,
                        cwd=tmp_path,
                    )


# -- dispatch/relay error handling -------------------------


def test_nonzero_exit_raises(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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


def test_timeout_exit_code_raises_timeout(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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
    agent = _agent(tmp_path)
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


# -- verdict content validation ----------------------------


def test_finding_id_mismatch_retries_then_raises(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay(_relay_response())

    def fake_dispatch(*_a: object, **_kw: object) -> None:
        _write_verdict(tmp_path, json.dumps(_valid_verdict(finding_id=99)))

    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with patch.object(agent, "_dispatch_prompt", side_effect=fake_dispatch):
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


def test_missing_verdict_field_retries_then_raises(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    mock_proc = _mock_relay(_relay_response())
    incomplete = {
        "finding_id": _FINDING_ID,
        "confidence": "confirmed",
    }

    def fake_dispatch(*_a: object, **_kw: object) -> None:
        _write_verdict(tmp_path, json.dumps(incomplete))

    with patch("subprocess.Popen", return_value=mock_proc):
        with agent.prepare_session(project="p", run_id=1, app_root=tmp_path):
            with patch.object(agent, "_dispatch_prompt", side_effect=fake_dispatch):
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
