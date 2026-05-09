"""Unit tests for retry-once behavior in the triage orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.locking.exceptions import FindingsBusy
from application.triage.orchestrator import run_triage
from application.triage.runner import TriageResult

_BUSY = FindingsBusy(conflicting_ids=[1], holders={1: "triage-run:1"})
_SUCCESS = TriageResult(sessions_run=1, success=1, failed=0, incomplete=0)


class TestRetryOnce:
    @patch("application.triage.orchestrator.time.sleep")
    @patch("application.triage.orchestrator.build_triage_runner")
    def test_retries_once_on_busy_then_succeeds(
        self, mock_build_runner: MagicMock, mock_sleep: MagicMock
    ) -> None:
        runner = MagicMock()
        runner.run.side_effect = [_BUSY, _SUCCESS]
        mock_build_runner.return_value = runner

        result = run_triage("test-project", MagicMock(), app_root=Path("/unused"))

        assert result == {
            "sessions_run": 1,
            "success": 1,
            "failed": 0,
            "incomplete": 0,
        }
        mock_sleep.assert_called_once_with(5)
        assert runner.run.call_count == 2

    @patch("application.triage.orchestrator.time.sleep")
    @patch("application.triage.orchestrator.build_triage_runner")
    def test_propagates_findings_busy_on_second_failure(
        self, mock_build_runner: MagicMock, mock_sleep: MagicMock
    ) -> None:
        runner = MagicMock()
        runner.run.side_effect = _BUSY
        mock_build_runner.return_value = runner

        with pytest.raises(FindingsBusy):
            run_triage(
                "test-project",
                MagicMock(),
                app_root=Path("/unused"),
            )

        mock_sleep.assert_called_once_with(5)
        assert runner.run.call_count == 2

    @patch("application.triage.orchestrator.build_triage_runner")
    def test_no_sleep_when_first_call_succeeds(
        self, mock_build_runner: MagicMock
    ) -> None:
        runner = MagicMock()
        runner.run.return_value = _SUCCESS
        mock_build_runner.return_value = runner

        with patch("application.triage.orchestrator.time.sleep") as mock_sleep:
            run_triage(
                "test-project",
                MagicMock(),
                app_root=Path("/unused"),
            )

        mock_sleep.assert_not_called()
        assert runner.run.call_count == 1
