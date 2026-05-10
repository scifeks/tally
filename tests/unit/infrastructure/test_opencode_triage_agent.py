"""Unit tests for OpenCodeTriageAgent.

Pin the argv shape, stdin piping, NDJSON event stream parsing, session
prep, and error translation of the one-shot OpenCode adapter running
inside a Docker container. ``subprocess.run`` is patched throughout.
"""

from __future__ import annotations

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


def _multi_text_event_stream(
    *text_parts: str,
) -> str:
    events: list[str] = []
    events.append(
        json.dumps(
            {
                "type": "step_start",
                "timestamp": 1000,
                "sessionID": "ses_test",
                "part": {"type": "step-start"},
            }
        )
    )
    for i, part in enumerate(text_parts):
        events.append(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1001 + i,
                    "sessionID": "ses_test",
                    "part": {"type": "text", "text": part},
                }
            )
        )
    events.append(
        json.dumps(
            {
                "type": "step_finish",
                "timestamp": 1100,
                "sessionID": "ses_test",
                "part": {"type": "step-finish"},
            }
        )
    )
    return "\n".join(events) + "\n"


def _ok_completed(verdict_text: str) -> MagicMock:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = _opencode_event_stream(verdict_text)
    completed.stderr = ""
    return completed


def _happy_completed() -> MagicMock:
    return _ok_completed(json.dumps(_valid_verdict()))


# -- session prep ----------------------------------------------------


def test_prepare_session_yields_app_root_as_cwd(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent(compose_path=tmp_path / "compose.yaml")
    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path) as session:
        assert session.cwd == tmp_path


def test_prepare_session_does_not_create_config(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent(compose_path=tmp_path / "compose.yaml")
    with agent.prepare_session(project="proj", run_id=42, app_root=tmp_path):
        assert not any(tmp_path.iterdir())


# -- argv shape ------------------------------------------------------


def test_command_starts_with_docker_compose(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "docker" in cmd
    assert "compose" in cmd
    assert "-f" in cmd
    assert str(_COMPOSE_PATH) in cmd


def test_exec_flags_present(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "exec" in cmd
    assert "-T" in cmd
    assert "triage-agent" in cmd


def test_opencode_binary_after_service_name(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "triage-agent" in cmd
    assert "opencode" in cmd


def test_run_subcommand_present(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "opencode" in cmd
    assert "run" in cmd


def test_dir_is_workspace(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "--dir" in cmd
    assert "/workspace" in cmd


def test_json_format_flag_present(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "--format" in cmd
    assert "json" in cmd


def test_dangerously_skip_permissions_present(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_opencode_config_env_in_command(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "-e" in cmd
    assert "OPENCODE_CONFIG=/etc/opencode/opencode.json" in cmd


def test_prompt_passed_via_stdin(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "hello finding 42",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[1]["input"] == "hello finding 42"


def test_no_host_cwd_passed(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert "cwd" not in m.call_args[1]


def test_no_host_env_override(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert "env" not in m.call_args[1]


# -- happy path ------------------------------------------------------


def test_happy_path_returns_verdict(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()):
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


def test_multiple_text_events_concatenated(
    tmp_path: Path,
) -> None:
    verdict = _valid_verdict()
    verdict_json = json.dumps(verdict)
    half = len(verdict_json) // 2
    part_a = verdict_json[:half]
    part_b = verdict_json[half:]

    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = _multi_text_event_stream(part_a, part_b)
    completed.stderr = ""
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        result = agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert isinstance(result, Verdict)
    assert result.finding_id == _FINDING_ID


def test_multi_json_in_text_succeeds(
    tmp_path: Path,
) -> None:
    verdict_json = json.dumps(_valid_verdict())
    extra_json = json.dumps({"extra": "data"})
    combined = verdict_json + "\n" + extra_json
    agent = _agent()
    with patch(
        "subprocess.run",
        return_value=_ok_completed(combined),
    ):
        verdict = agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert isinstance(verdict, Verdict)
    assert verdict.finding_id == _FINDING_ID


# -- error handling --------------------------------------------------


def test_nonzero_exit_raises(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 1
    completed.stderr = "something went wrong"
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="exited with code 1"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_timeout_propagates(tmp_path: Path) -> None:
    agent = _agent()
    exc = subprocess.TimeoutExpired(cmd=["docker"], timeout=60)
    with patch("subprocess.run", side_effect=exc):
        with pytest.raises(subprocess.TimeoutExpired):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_docker_not_found_propagates(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch(
        "subprocess.run",
        side_effect=FileNotFoundError("no docker"),
    ):
        with pytest.raises(FileNotFoundError):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_empty_stdout_raises(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = ""
    completed.stderr = ""
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="empty stdout"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_no_text_events_raises(tmp_path: Path) -> None:
    non_text_stream = "\n".join(
        [
            json.dumps({"type": "step_start", "part": {}}),
            json.dumps({"type": "step_finish", "part": {}}),
        ]
    )
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = non_text_stream
    completed.stderr = ""
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="no text events"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_malformed_verdict_json_raises(
    tmp_path: Path,
) -> None:
    agent = _agent()
    with patch(
        "subprocess.run",
        return_value=_ok_completed("not valid json {{{"),
    ):
        with pytest.raises(VerdictParseError):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_finding_id_mismatch_raises(
    tmp_path: Path,
) -> None:
    verdict_text = json.dumps(_valid_verdict(finding_id=99))
    agent = _agent()
    with patch(
        "subprocess.run",
        return_value=_ok_completed(verdict_text),
    ):
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
    verdict_text = json.dumps(incomplete)
    agent = _agent()
    with patch(
        "subprocess.run",
        return_value=_ok_completed(verdict_text),
    ):
        with pytest.raises(VerdictParseError, match="missing fields"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )
