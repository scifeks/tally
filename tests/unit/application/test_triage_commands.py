"""Unit tests for TriageCommands (application.repl.commands.triage_commands)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.triage_commands import TriageCommands


@pytest.fixture()
def mock_repl() -> MagicMock:
    repl = MagicMock()
    repl.active_project = "test-project"
    return repl


@pytest.fixture()
def commands(mock_repl: MagicMock) -> TriageCommands:
    return TriageCommands(mock_repl)


class TestTriageCommands:
    def test_no_active_project_prints_error_and_returns(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        mock_repl.active_project = None
        with (
            patch("application.repl.commands.triage_commands.run_triage") as mock_run,
            patch(
                "application.repl.commands.triage_commands.run_triage_batch_only"
            ) as mock_batch,
            patch(
                "application.repl.commands.triage_commands.run_triage_dry_run"
            ) as mock_dry,
        ):
            commands.cmd_triage("triage", [])

        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "No active" in printed
        mock_run.assert_not_called()
        mock_batch.assert_not_called()
        mock_dry.assert_not_called()

    def test_batch_flag_calls_run_triage_batch_only(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only",
            return_value=3,
        ) as mock_batch:
            commands.cmd_triage("triage", ["--batch"])

        mock_batch.assert_called_once_with("test-project")
        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "3" in printed

    def test_dry_run_flag_calls_run_triage_dry_run(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with patch(
            "application.repl.commands.triage_commands.run_triage_dry_run",
            return_value=2,
        ) as mock_dry:
            commands.cmd_triage("triage", ["--dry-run"])

        mock_dry.assert_called_once_with("test-project")

    def test_default_path_cancelled_when_user_enters_n(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with (
            patch("builtins.input", return_value="n"),
            patch("application.repl.commands.triage_commands.run_triage") as mock_run,
        ):
            commands.cmd_triage("triage", [])

        mock_run.assert_not_called()
        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "cancelled" in printed.lower()

    def test_default_path_proceeds_when_user_enters_y(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        result = {"sessions_run": 1, "success": 1, "failed": 0, "incomplete": 0}
        with (
            patch("builtins.input", return_value="y"),
            patch(
                "application.repl.commands.triage_commands.run_triage",
                return_value=result,
            ) as mock_run,
        ):
            commands.cmd_triage("triage", [])

        mock_run.assert_called_once_with("test-project")
