"""Adapter contract tests for OpenCodeTriageAgent.

Pin the argv shape, stdin piping, JSON event stream parsing, and error
translation of the one-shot OpenCode adapter. ``subprocess.run`` is
patched so the command shape can be inspected and exceptions injected.
"""

# ruff: noqa: E402, I001

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
from infrastructure.agents.opencode_triage_agent import (  # noqa: E402
    OpenCodeTriageAgent,
)

pytestmark = pytest.mark.integration

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
                "part": {"type": "text", "text": verdict_text},
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


def _ok_completed(verdict_text: str) -> MagicMock:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = _opencode_event_stream(verdict_text)
    completed.stderr = ""
    return completed


def _happy_completed() -> MagicMock:
    return _ok_completed(json.dumps(_valid_verdict()))


# -- argv shape tests -----------------------------------------------


def test_invokes_opencode_binary(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[0][0][0] == "opencode"


def test_run_subcommand_present(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[0][0][1] == "run"


def test_dir_flag_present_with_cwd(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    idx = cmd.index("--dir")
    assert cmd[idx + 1] == str(tmp_path)


def test_json_format_flag_present(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    idx = cmd.index("--format")
    assert cmd[idx + 1] == "json"


def test_dangerously_skip_permissions_present(
    tmp_path: Path,
) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    cmd = m.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_prompt_passed_via_stdin(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "hello finding 42",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[1]["input"] == "hello finding 42"


def test_cwd_passed_to_subprocess(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=_happy_completed()) as m:
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )
    assert m.call_args[1]["cwd"] == str(tmp_path)


def test_permission_config_passed_via_env(
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}

    def _capture(args, **kwargs):
        assert args
        config_path = kwargs["env"]["OPENCODE_CONFIG"]
        captured["content"] = Path(config_path).read_text()
        return _happy_completed()

    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", side_effect=_capture):
        agent.run_triage(
            "prompt",
            finding_id=_FINDING_ID,
            timeout_seconds=60,
            cwd=tmp_path,
        )

    config = json.loads(captured["content"])
    assert "mcp" not in config
    perm = config["permission"]
    assert perm["read"] == {"*": "allow"}
    assert perm["edit"] == "deny"
    assert perm["bash"] == {"*": "deny"}
    assert perm["write"] == {"*": "deny"}
    assert perm["webfetch"] == "deny"


# -- happy path ------------------------------------------------------


def test_happy_path_returns_verdict(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
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
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="exited with code 1"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_timeout_propagates(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    exc = subprocess.TimeoutExpired(cmd=["opencode"], timeout=60)
    with patch("subprocess.run", side_effect=exc):
        with pytest.raises(subprocess.TimeoutExpired):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_binary_not_found_propagates(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
    with patch(
        "subprocess.run",
        side_effect=FileNotFoundError("no opencode"),
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
    agent = OpenCodeTriageAgent()
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
    agent = OpenCodeTriageAgent()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(VerdictParseError, match="no text events"):
            agent.run_triage(
                "prompt",
                finding_id=_FINDING_ID,
                timeout_seconds=60,
                cwd=tmp_path,
            )


def test_malformed_verdict_json_raises(tmp_path: Path) -> None:
    agent = OpenCodeTriageAgent()
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
