"""Unit tests for TriageCommands (application.repl.commands.triage_commands)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.triage_commands import TriageCommands
from application.triage.readiness import TriageReadiness


def _readiness_enabled(
    provider: str = "claude_code",
) -> TriageReadiness:
    return TriageReadiness(
        provider=provider,
        backend_label=provider,
        enabled=True,
        reason=None,
    )


def _readiness_disabled(reason: str) -> TriageReadiness:
    return TriageReadiness(
        provider="",
        backend_label=None,
        enabled=False,
        reason=reason,
    )


@pytest.fixture()
def mock_repl() -> MagicMock:
    repl = MagicMock()
    repl.active_project = "test-project"
    repl.triage_readiness = _readiness_enabled()
    return repl


@pytest.fixture()
def commands(mock_repl: MagicMock) -> TriageCommands:
    return TriageCommands(mock_repl)


class TestTriageCommands:
    def test_no_active_project_prints_error_and_returns(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        mock_repl.active_project = None
        with patch("application.repl.commands.triage_commands.create_triage_service"):
            commands.cmd_triage("triage", [])

        mock_repl.console.print.assert_called()

    def test_batch_flag_calls_run_triage_batch_only(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only",
            return_value=3,
        ) as mock_batch:
            commands.cmd_triage("triage", ["--batch"])

        mock_batch.assert_called_once()
        mock_repl.console.print.assert_called()

    def test_dry_run_flag_calls_run_triage_dry_run(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with (
            patch(
                "application.repl.commands.triage_commands.run_triage_dry_run",
                return_value=2,
            ) as mock_dry,
            patch("application.repl.commands.triage_commands.make_store") as mock_store,
            patch(
                "application.repl.commands.triage_commands.load_active_repos",
                return_value=[],
            ),
        ):
            mock_run_repo = MagicMock()
            mock_finding_repo = MagicMock()
            mock_triage_repo = MagicMock()
            mock_audit_repo = MagicMock()
            mock_store.return_value = (
                mock_run_repo,
                mock_finding_repo,
                mock_triage_repo,
                mock_audit_repo,
            )
            commands.cmd_triage("triage", ["--dry-run"])

        mock_dry.assert_called_once()

    def test_default_path_cancelled_when_user_enters_n(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with (
            patch("builtins.input", return_value="n"),
            patch(
                "application.repl.commands.triage_commands.create_triage_service"
            ) as mock_service,
        ):
            commands.cmd_triage("triage", [])

        mock_service.assert_not_called()

    def test_default_path_proceeds_when_user_enters_y(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        row = MagicMock()
        row.id = 42
        row.archived_at = None
        mock_repl.project_registry.resolve_by_name.return_value = row

        handle = MagicMock()
        service = MagicMock()
        service.start_triage.return_value = handle

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
            ) as mock_service_fn,
        ):
            commands.cmd_triage("triage", [])

        mock_service_fn.assert_called_once()
        service.start_triage.assert_called_once()

    def test_disabled_provider_prints_error_before_running(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        mock_repl.triage_readiness = _readiness_disabled("Triage disabled in config")
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only"
        ) as mock_batch:
            commands.cmd_triage("triage", ["--batch"])

        mock_batch.assert_not_called()
