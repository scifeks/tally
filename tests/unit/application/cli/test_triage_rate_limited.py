"""CLI triage command exits with RATE_LIMITED on a rate-limited result."""

from __future__ import annotations

import sys
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.cli.commands.triage import _full_triage_mode  # noqa: E402
from application.cli.exit_codes import RATE_LIMITED, SUCCESS  # noqa: E402


def _make_handle(result_dict: dict) -> MagicMock:
    future: Future[dict] = Future()
    future.set_result(result_dict)
    handle = MagicMock()
    handle.result = future
    return handle


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


def test_rate_limited_result_exits_with_rate_limited_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = MagicMock()
    service.start_triage.return_value = _make_handle(_RATE_LIMITED_RESULT)

    with (
        patch(
            "application.cli.commands.triage.ensure_image",
        ),
        patch(
            "application.cli.commands.triage.ensure_containers",
        ),
        patch(
            "application.cli.commands.triage.resolve_triage_config",
            return_value=MagicMock(provider_name="claude", base_url="", model="sonnet"),
        ),
        patch(
            "application.cli.commands.triage.create_triage_service",
            return_value=service,
        ),
        patch(
            "application.cli.commands.triage.load_active_repos",
            return_value=[],
        ),
    ):
        code = _full_triage_mode(
            project_id=1,
            project_registry=MagicMock(),
            tool_registry=MagicMock(),
            base_path=Path("/app"),
            project_name="proj",
        )

    assert code == RATE_LIMITED
    captured = capsys.readouterr()
    assert "rate limit" in captured.err.lower()
    assert "resume" in captured.err.lower()


def test_success_result_exits_with_success(capsys: pytest.CaptureFixture[str]) -> None:
    service = MagicMock()
    service.start_triage.return_value = _make_handle(_SUCCESS_RESULT)

    with (
        patch(
            "application.cli.commands.triage.ensure_image",
        ),
        patch(
            "application.cli.commands.triage.ensure_containers",
        ),
        patch(
            "application.cli.commands.triage.resolve_triage_config",
            return_value=MagicMock(provider_name="claude", base_url="", model="sonnet"),
        ),
        patch(
            "application.cli.commands.triage.create_triage_service",
            return_value=service,
        ),
        patch(
            "application.cli.commands.triage.load_active_repos",
            return_value=[],
        ),
    ):
        code = _full_triage_mode(
            project_id=1,
            project_registry=MagicMock(),
            tool_registry=MagicMock(),
            base_path=Path("/app"),
            project_name="proj",
        )

    assert code == SUCCESS
    captured = capsys.readouterr()
    assert "3 sessions run" in captured.out
