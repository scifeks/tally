"""Unit tests for TriageCommands (application.repl.commands.triage_commands)."""

from __future__ import annotations

from pathlib import Path
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
        with patch(
            "application.repl.commands.triage_commands.TriageService"
        ) as mock_service:
            commands.cmd_triage("triage", [])

        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "No active" in printed
        mock_service.for_project.assert_not_called()

    def test_batch_flag_calls_run_triage_batch_only(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only",
            return_value=3,
        ) as mock_batch:
            commands.cmd_triage("triage", ["--batch"])

        mock_batch.assert_called_once_with(
            "test-project",
            mock_repl.tool_registry,
            app_root=Path(mock_repl.base_path),
        )
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

        mock_dry.assert_called_once_with(
            "test-project",
            mock_repl.tool_registry,
            app_root=Path(mock_repl.base_path),
        )

    def test_default_path_cancelled_when_user_enters_n(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        with (
            patch("builtins.input", return_value="n"),
            patch(
                "application.repl.commands.triage_commands.TriageService"
            ) as mock_service,
        ):
            commands.cmd_triage("triage", [])

        mock_service.for_project.assert_not_called()
        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "cancelled" in printed.lower()

    def test_default_path_proceeds_when_user_enters_y(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        result = {
            "sessions_run": 1,
            "success": 1,
            "failed": 0,
            "incomplete": 0,
        }

        row = MagicMock()
        row.id = 42
        row.archived_at = None
        mock_repl.project_registry.resolve_by_name.return_value = row

        handle = MagicMock()
        handle.result.result.return_value = result
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
                "application.repl.commands.triage_commands.TriageService"
            ) as mock_service_cls,
        ):
            mock_service_cls.for_project.return_value = service
            commands.cmd_triage("triage", [])

        mock_service_cls.for_project.assert_called_once_with(
            mock_repl.project_registry, 42
        )
        service.start_triage.assert_called_once()
        kwargs = service.start_triage.call_args.kwargs
        assert kwargs["project_id"] == 42
        assert kwargs["project_name"] == "test-project"
        assert kwargs["tool_registry"] is mock_repl.tool_registry

    def test_disabled_provider_prints_error_before_running(
        self, commands: TriageCommands, mock_repl: MagicMock
    ) -> None:
        mock_repl.triage_readiness = _readiness_disabled("Triage disabled in config")
        with patch(
            "application.repl.commands.triage_commands.run_triage_batch_only"
        ) as mock_batch:
            commands.cmd_triage("triage", ["--batch"])

        mock_batch.assert_not_called()
        printed = " ".join(str(call) for call in mock_repl.console.print.call_args_list)
        assert "Triage disabled in config" in printed
