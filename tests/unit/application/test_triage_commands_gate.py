"""Tests for the Claude Code gate in TriageCommands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.triage_commands import TriageCommands


def _repl(active_project: str | None = "test-project") -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    return repl


def _runtime(installed: bool) -> MagicMock:
    svc = MagicMock()
    svc.is_installed.return_value = installed
    return svc


class TestTriageCommandsClaudeGate:
    def _assert_gated(self, args: list[str]) -> None:
        repl = _repl()
        cmds = TriageCommands(repl, runtime_service=_runtime(installed=False))
        with (
            patch(
                "application.repl.commands.triage_commands.TriageService"
            ) as mock_service,
            patch(
                "application.repl.commands.triage_commands.run_triage_batch_only"
            ) as rb,
            patch("application.repl.commands.triage_commands.run_triage_dry_run") as rd,
        ):
            cmds.cmd_triage("triage", args)
        mock_service.for_project.assert_not_called()
        rb.assert_not_called()
        rd.assert_not_called()
        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "Claude Code" in printed

    def test_no_args_gated(self) -> None:
        self._assert_gated([])

    def test_batch_flag_gated(self) -> None:
        self._assert_gated(["--batch"])

    def test_dry_run_flag_gated(self) -> None:
        self._assert_gated(["--dry-run"])

    def test_claude_present_proceeds_to_project_check(self) -> None:
        repl = _repl(active_project=None)
        cmds = TriageCommands(repl, runtime_service=_runtime(installed=True))
        with patch(
            "application.repl.commands.triage_commands.TriageService"
        ) as mock_service:
            cmds.cmd_triage("triage", [])
        mock_service.for_project.assert_not_called()
        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "No active" in printed

    def test_no_runtime_service_skips_gate(self) -> None:
        repl = _repl(active_project=None)
        cmds = TriageCommands(repl, runtime_service=None)
        with patch(
            "application.repl.commands.triage_commands.TriageService"
        ) as mock_service:
            cmds.cmd_triage("triage", [])
        mock_service.for_project.assert_not_called()
        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "No active" in printed
