"""Tests for the SyncCommand REPL handler."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.export import ExportResult  # noqa: E402
from application.repl.commands.sync import (  # noqa: E402
    SyncCommand,
)
from domain.projects.entry import ProjectRow  # noqa: E402

_PROJECT = "testproj"
_PROJECT_ID = 7


def _mock_repl(
    active_project: str | None = _PROJECT,
) -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/tally"
    if active_project is not None:
        repl.project_registry.resolve_by_name.return_value = ProjectRow(
            id=_PROJECT_ID,
            name=active_project,
            path="/tmp/tally/projects/" + active_project,
            created_at="2026-05-13T00:00:00Z",
        )
    return repl


def _ok_result(exported: int = 10) -> ExportResult:
    return ExportResult(
        success=True,
        findings_exported=exported,
        findings_failed=0,
    )


def _failed_result() -> ExportResult:
    return ExportResult(
        success=False,
        findings_exported=0,
        findings_failed=0,
        errors=("Connection refused",),
    )


_FACTORY = "factories.export.create_export_service"


class TestSyncMissingIntegration:
    def test_prints_usage_when_no_args(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        cmd.cmd_sync("sync", [])
        printed = repl.console.print.call_args[0][0]
        assert "Usage:" in printed

    def test_prints_usage_when_only_flags(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        cmd.cmd_sync("sync", ["--run-id=3"])
        printed = repl.console.print.call_args[0][0]
        assert "Usage:" in printed


class TestSyncUnknownIntegration:
    def test_prints_error_for_unknown_name(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        cmd.cmd_sync("sync", ["--integration=jira"])
        printed = repl.console.print.call_args[0][0]
        assert "Unknown integration" in printed
        assert "jira" in printed


class TestSyncNoActiveProject:
    def test_prints_warning(self) -> None:
        repl = _mock_repl(active_project=None)
        cmd = SyncCommand(repl)
        cmd.cmd_sync("sync", ["--integration=defectdojo"])
        printed = repl.console.print.call_args[0][0]
        assert "No active project" in printed


class TestSyncTestConnection:
    def test_prints_success(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.test_connection.return_value = True
        with patch(_FACTORY, return_value=svc):
            cmd.cmd_sync(
                "sync",
                [
                    "--integration=defectdojo",
                    "--test-connection",
                ],
            )
        svc.test_connection.assert_called_once()
        printed = repl.console.print.call_args[0][0]
        assert "successful" in printed

    def test_prints_failure(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.test_connection.return_value = False
        with patch(_FACTORY, return_value=svc):
            cmd.cmd_sync(
                "sync",
                [
                    "--integration=defectdojo",
                    "--test-connection",
                ],
            )
        printed = repl.console.print.call_args[0][0]
        assert "failed" in printed


class TestSyncExport:
    def test_calls_export_without_run_id(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = _ok_result(42)
        with patch(_FACTORY, return_value=svc) as factory:
            cmd.cmd_sync("sync", ["--integration=defectdojo"])
        svc.export.assert_called_once_with()
        assert factory.call_args.kwargs["run_id"] is None

    def test_calls_export_with_run_id(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = _ok_result(5)
        with patch(_FACTORY, return_value=svc) as factory:
            cmd.cmd_sync(
                "sync",
                [
                    "--integration=defectdojo",
                    "--run-id=3",
                ],
            )
        svc.export.assert_called_once_with()
        assert factory.call_args.kwargs["run_id"] == 3

    def test_prints_success_message(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = _ok_result(10)
        with patch(_FACTORY, return_value=svc):
            cmd.cmd_sync("sync", ["--integration=defectdojo"])
        printed = repl.console.print.call_args[0][0]
        assert "Sync complete" in printed
        assert "10 exported" in printed

    def test_prints_failed_count(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = ExportResult(
            success=True,
            findings_exported=8,
            findings_failed=2,
        )
        with patch(_FACTORY, return_value=svc):
            cmd.cmd_sync("sync", ["--integration=defectdojo"])
        printed = repl.console.print.call_args[0][0]
        assert "2" in printed
        assert "failed to map" in printed

    def test_prints_errors_on_failure(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = _failed_result()
        with patch(_FACTORY, return_value=svc):
            cmd.cmd_sync("sync", ["--integration=defectdojo"])
        calls = [str(c) for c in repl.console.print.call_args_list]
        assert any("Sync failed" in c for c in calls)
        assert any("Connection refused" in c for c in calls)


class TestSyncInvalidRunId:
    def test_prints_error(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        cmd.cmd_sync(
            "sync",
            ["--integration=defectdojo", "--run-id=abc"],
        )
        printed = repl.console.print.call_args[0][0]
        assert "Invalid run ID" in printed


class TestSyncServiceBuildFailure:
    def test_prints_exception_message(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        with patch(
            _FACTORY,
            side_effect=ValueError("DefectDojo connection not configured."),
        ):
            cmd.cmd_sync("sync", ["--integration=defectdojo"])
        printed = repl.console.print.call_args[0][0]
        assert "not configured" in printed


class TestSyncEngagementType:
    def test_passes_engagement_type_to_factory(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = _ok_result(5)
        with patch(_FACTORY, return_value=svc) as factory:
            cmd.cmd_sync(
                "sync",
                [
                    "--integration=defectdojo",
                    "--engagement-type=CI/CD",
                ],
            )
        factory.assert_called_once()
        call_kwargs = factory.call_args
        assert call_kwargs.kwargs["engagement_type_override"] == "CI/CD"

    def test_defaults_to_none_when_not_set(self) -> None:
        repl = _mock_repl()
        cmd = SyncCommand(repl)
        svc = MagicMock()
        svc.export.return_value = _ok_result(5)
        with patch(_FACTORY, return_value=svc) as factory:
            cmd.cmd_sync("sync", ["--integration=defectdojo"])
        factory.assert_called_once()
        call_kwargs = factory.call_args
        assert call_kwargs.kwargs["engagement_type_override"] is None
