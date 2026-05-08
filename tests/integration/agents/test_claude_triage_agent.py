"""Adapter contract tests for ClaudeTriageAgent.

Pin the argv shape, stdin piping, JSON wrapper parsing, and error
translation of the one-shot Claude Code adapter running inside a
Docker container. ``subprocess.run`` is patched so the command
shape can be inspected and exceptions injected.
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
from infrastructure.agents.claude_triage_agent import (
    ClaudeTriageAgent,
)

pytestmark = pytest.mark.integration

_MODEL = "sonnet"
_FINDING_ID = 42
_COMPOSE_PATH = Path("/app/docker/triage-agent/docker-compose.yaml")


def _agent() -> ClaudeTriageAgent:
    return ClaudeTriageAgent(model=_MODEL, compose_path=_COMPOSE_PATH)


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


def _claude_wrapper(
    verdict_text: str,
    *,
    is_error: bool = False,
) -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "error" if is_error else "success",
            "is_error": is_error,
            "result": verdict_text,
        }
    )


def _ok_completed(verdict_text: str) -> MagicMock:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = _claude_wrapper(verdict_text)
    completed.stderr = ""
    return completed


def _happy_completed() -> MagicMock:
    return _ok_completed(json.dumps(_valid_verdict()))


# -- argv shape tests -----------------------------------------------


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
    assert cmd[:2] == ["docker", "compose"]
    assert cmd[2] == "-f"
    assert cmd[3] == str(_COMPOSE_PATH)


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


def test_claude_binary_after_service_name(
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
    svc_idx = cmd.index("triage-agent")
    assert cmd[svc_idx + 1] == "claude"


def test_print_and_json_flags(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "--print" in cmd
    idx = cmd.index("--output-format")
    assert cmd[idx + 1] == "json"


def test_tools_disabled(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    idx = cmd.index("--tools")
    assert cmd[idx + 1] == ""


def test_model_passed_from_constructor(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model="opus", compose_path=_COMPOSE_PATH)
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    idx = cmd.index("--model")
    assert cmd[idx + 1] == "opus"


def test_add_dir_is_workspace(tmp_path: Path) -> None:
    agent = _agent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    idx = cmd.index("--add-dir")
    assert cmd[idx + 1] == "/workspace"


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


# -- happy path ------------------------------------------------------


def test_happy_path_returns_verdict(tmp_path: Path) -> None:
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


def test_docker_not_found_propagates(tmp_path: Path) -> None:
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


def test_malformed_wrapper_json_raises(
    tmp_path: Path,
) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "not json at all"
    completed.stderr = ""
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="not valid JSON"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_wrapper_is_error_raises(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = _claude_wrapper("oops", is_error=True)
    completed.stderr = ""
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="reported an error"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_wrapper_missing_result_field_raises(
    tmp_path: Path,
) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = json.dumps({"type": "result", "is_error": False})
    completed.stderr = ""
    agent = _agent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="missing 'result'"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )
