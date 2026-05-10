"""Tests triage readiness gating."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.triage_commands import TriageCommands
from application.triage.readiness import TriageReadiness


def _repl(active_project: str | None = "test-project") -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.triage_readiness = TriageReadiness(
        provider="claude_code",
        backend_label="Claude Code",
        enabled=True,
        reason=None,
    )
    return repl


def _readiness_disabled(
    provider: str = "claude_code",
    label: str = "Claude Code",
    reason: str = "Docker is not installed or not running",
) -> TriageReadiness:
    return TriageReadiness(
        provider=provider,
        backend_label=label,
        enabled=False,
        reason=reason,
    )


def _readiness_enabled(
    provider: str = "claude_code",
    label: str = "Claude Code",
) -> TriageReadiness:
    return TriageReadiness(
        provider=provider,
        backend_label=label,
        enabled=True,
        reason=None,
    )


class TestTriageCommandsReadinessGate:
    def _assert_gated(self, args: list[str], reason: str) -> None:
        repl = _repl()
        repl.triage_readiness = _readiness_disabled(reason=reason)
        cmds = TriageCommands(repl)
        with (
            patch(
                "application.repl.commands.triage_commands.create_triage_service"
            ) as mock_service,
            patch(
                "application.repl.commands.triage_commands.run_triage_batch_only"
            ) as rb,
            patch("application.repl.commands.triage_commands.run_triage_dry_run") as rd,
        ):
            cmds.cmd_triage("triage", args)
        mock_service.assert_not_called()
        rb.assert_not_called()
        rd.assert_not_called()
        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert reason in printed

    def test_no_args_gated(self) -> None:
        self._assert_gated([], "Docker is not installed or not running")

    def test_batch_flag_gated(self) -> None:
        self._assert_gated(
            ["--batch"],
            "Docker is not installed or not running",
        )

    def test_dry_run_flag_gated(self) -> None:
        self._assert_gated(
            ["--dry-run"],
            "Docker is not installed or not running",
        )

    def test_enabled_proceeds_to_project_check(self) -> None:
        repl = _repl(active_project=None)
        repl.triage_readiness = _readiness_enabled()
        cmds = TriageCommands(repl)
        with patch(
            "application.repl.commands.triage_commands.create_triage_service"
        ) as mock_service:
            cmds.cmd_triage("triage", [])
        mock_service.assert_not_called()
        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "No active" in printed

    def test_disabled_opencode_is_gated(self) -> None:
        repl = _repl()
        repl.triage_readiness = _readiness_disabled(
            provider="open_code",
            label="OpenCode",
            reason="Docker is not installed or not running",
        )
        cmds = TriageCommands(repl)
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only"
        ) as mock_batch:
            cmds.cmd_triage("triage", ["--batch"])
        mock_batch.assert_not_called()
        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "Docker is not installed" in printed

    def test_enabled_opencode_proceeds(self) -> None:
        repl = _repl()
        repl.triage_readiness = _readiness_enabled(
            provider="open_code",
            label="OpenCode",
        )
        cmds = TriageCommands(repl)
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only",
            return_value=1,
        ) as mock_batch:
            cmds.cmd_triage("triage", ["--batch"])
        mock_batch.assert_called_once()
