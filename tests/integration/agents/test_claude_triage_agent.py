"""Adapter contract tests for ClaudeTriageAgent.

Pin the argv shape, stdin piping, JSON wrapper parsing, and error
translation of the one-shot Claude Code adapter. ``subprocess.run``
is patched so the command shape can be inspected and exceptions injected.
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

from application.triage.verdict import (  # noqa: E402
    Verdict,
    VerdictParseError,
)
from infrastructure.agents.claude_triage_agent import (  # noqa: E402
    ClaudeTriageAgent,
)

pytestmark = pytest.mark.integration

_MODEL = "sonnet"
_FINDING_ID = 42


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


def test_invokes_claude_binary(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[0][0][0] == "claude"


def test_print_and_json_flags(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
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
    agent = ClaudeTriageAgent(model=_MODEL)
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
    agent = ClaudeTriageAgent(model="opus")
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


def test_add_dir_matches_cwd(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    idx = cmd.index("--add-dir")
    assert cmd[idx + 1] == str(tmp_path)


def test_prompt_passed_via_stdin(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "hello finding 42",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[1]["input"] == "hello finding 42"


def test_cwd_passed_to_subprocess(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[1]["cwd"] == str(tmp_path)


# -- happy path ------------------------------------------------------


def test_happy_path_returns_verdict(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
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
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="exited with code 1"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_timeout_propagates(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
    exc = subprocess.TimeoutExpired(cmd=["claude"], timeout=60)
    with patch("subprocess.run", side_effect=exc):
        with pytest.raises(subprocess.TimeoutExpired):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_binary_not_found_propagates(tmp_path: Path) -> None:
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", side_effect=FileNotFoundError("no claude")):
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
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="empty stdout"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_malformed_wrapper_json_raises(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "not json at all"
    completed.stderr = ""
    agent = ClaudeTriageAgent(model=_MODEL)
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
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="reported an error"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_wrapper_missing_result_field_raises(tmp_path: Path) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = json.dumps({"type": "result", "is_error": False})
    completed.stderr = ""
    agent = ClaudeTriageAgent(model=_MODEL)
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="missing 'result'"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )
