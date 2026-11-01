"""REPL triage command prints a yellow warning on rate-limited result."""

from __future__ import annotations

import sys
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.repl.commands.triage_commands import TriageCommands  # noqa: E402
from application.triage.readiness import TriageReadiness  # noqa: E402


def _make_handle(result_dict: dict) -> MagicMock:
    future: Future[dict] = Future()
    future.set_result(result_dict)
    handle = MagicMock()
    handle.result = future
    return handle


def _enabled_readiness() -> TriageReadiness:
    return TriageReadiness(
        provider="claude_code",
        backend_label="Claude Code",
        enabled=True,
        reason=None,
    )


def _mock_repl() -> MagicMock:
    repl = MagicMock()
    repl.active_project = "test-project"
    repl.triage_readiness = _enabled_readiness()
    return repl


def _printed(repl: MagicMock) -> str:
    return " ".join(str(c) for c in repl.console.print.call_args_list)


_RATE_LIMITED_RESULT = {
    "sessions_run": 2,
    "success": 1,
    "failed": 1,
    "incomplete": 0,
    "status": "rate_limited",
    "last_error_class": "rate_limit_plan",
}

_SUCCESS_RESULT = {
    "sessions_run": 3,
    "success": 3,
    "failed": 0,
    "incomplete": 0,
    "status": "completed",
    "last_error_class": None,
}


def test_rate_limited_result_prints_yellow_warning() -> None:
    repl = _mock_repl()
    row = MagicMock()
    row.id = 42
    row.archived_at = None
    repl.project_registry.resolve_by_name.return_value = row

    service = MagicMock()
    service.start_triage.return_value = _make_handle(_RATE_LIMITED_RESULT)

    with (
        patch("builtins.input", return_value="y"),
        patch(
            "application.repl.commands.triage_commands.ensure_triage_image",
            return_value=False,
        ),
        patch(
            "application.repl.commands.triage_commands.triage_image_ready",
            return_value=True,
        ),
        patch(
            "application.repl.commands.triage_commands.triage_containers_running",
            return_value=True,
        ),
        patch(
            "application.repl.commands.triage_commands.ensure_triage_containers",
            return_value=False,
        ),
        patch(
            "application.repl.commands.triage_commands.create_triage_service",
            return_value=service,
        ),
    ):
        cmds = TriageCommands(repl)
        cmds.cmd_triage("triage", [])

    output = _printed(repl)
    assert "yellow" in output.lower()
    assert "rate limit" in output.lower()
    assert "resume" in output.lower()


def test_success_result_prints_summary() -> None:
    repl = _mock_repl()
    row = MagicMock()
    row.id = 42
    row.archived_at = None
    repl.project_registry.resolve_by_name.return_value = row

    service = MagicMock()
    service.start_triage.return_value = _make_handle(_SUCCESS_RESULT)

    with (
        patch("builtins.input", return_value="y"),
        patch(
            "application.repl.commands.triage_commands.ensure_triage_image",
            return_value=False,
        ),
        patch(
            "application.repl.commands.triage_commands.triage_image_ready",
            return_value=True,
        ),
        patch(
            "application.repl.commands.triage_commands.triage_containers_running",
            return_value=True,
        ),
        patch(
            "application.repl.commands.triage_commands.ensure_triage_containers",
            return_value=False,
        ),
        patch(
            "application.repl.commands.triage_commands.create_triage_service",
            return_value=service,
        ),
    ):
        cmds = TriageCommands(repl)
        cmds.cmd_triage("triage", [])

    output = _printed(repl)
    assert "3 sessions run" in output
    assert "rate limit" not in output.lower()
