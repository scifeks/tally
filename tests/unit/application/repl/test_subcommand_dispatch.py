"""Tests that scan/triage sub-commands route through cmd_scan/cmd_triage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.scan_commands import ScanCommands
from application.repl.commands.triage_commands import TriageCommands


@pytest.fixture
def repl():
    repl_mock = MagicMock()
    repl_mock.active_project = "test-project"
    repl_mock.base_path = "/tmp/tally"
    repl_mock.project_registry = MagicMock()
    return repl_mock


class TestScanSubCommandDispatch:
    def test_scan_skills_dispatches(self, repl):
        """'scan skills' routes to cmd_scan_skills."""
        cmd = ScanCommands(repl)
        cmd.cmd_scan_skills = MagicMock()
        cmd.cmd_scan("scan", ["skills"])
        cmd.cmd_scan_skills.assert_called_once_with("scan", [])

    def test_scan_start_dispatches(self, repl):
        """'scan start --background' routes to cmd_scan_start."""
        cmd = ScanCommands(repl)
        cmd.cmd_scan_start = MagicMock()
        cmd.cmd_scan("scan", ["start", "--background"])
        cmd.cmd_scan_start.assert_called_once_with("scan", ["--background"])

    def test_scan_resume_dispatches(self, repl):
        """'scan resume 42' routes to cmd_scan_resume."""
        cmd = ScanCommands(repl)
        cmd.cmd_scan_resume = MagicMock()
        cmd.cmd_scan("scan", ["resume", "42"])
        cmd.cmd_scan_resume.assert_called_once_with("scan", ["42"])

    def test_scan_no_subcommand_falls_through(self, repl):
        """'scan --repo=foo' falls through to the legacy scan path."""
        cmd = ScanCommands(repl)
        with patch.object(cmd, "_cmd_scan_inner") as inner:
            cmd.cmd_scan("scan", ["--repo=foo"])
            inner.assert_called_once()


class TestTriageSubCommandDispatch:
    def test_triage_start_dispatches(self, repl):
        """'triage start --background' routes to cmd_triage_start."""
        cmd = TriageCommands(repl)
        cmd.cmd_triage_start = MagicMock()
        repl.triage_readiness = MagicMock(enabled=True)
        cmd.cmd_triage("triage", ["start", "--background"])
        cmd.cmd_triage_start.assert_called_once_with("triage", ["--background"])

    def test_triage_resume_dispatches(self, repl):
        """'triage resume 7' routes to cmd_triage_resume."""
        cmd = TriageCommands(repl)
        cmd.cmd_triage_resume = MagicMock()
        repl.triage_readiness = MagicMock(enabled=True)
        cmd.cmd_triage("triage", ["resume", "7"])
        cmd.cmd_triage_resume.assert_called_once_with("triage", ["7"])

    def test_triage_no_subcommand_falls_through(self, repl):
        """'triage --batch' falls through to the legacy triage path."""
        cmd = TriageCommands(repl)
        repl.triage_readiness = MagicMock(enabled=True)
        with patch("application.repl.commands.triage_commands.make_store") as ms:
            ms.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
            with patch(
                "application.repl.commands.triage_commands.load_active_repos",
                return_value=[],
            ):
                with patch(
                    "application.repl.commands.triage_commands.run_triage_batch_only",
                    return_value=0,
                ):
                    cmd.cmd_triage("triage", ["--batch"])
            repl.console.print.assert_called()


class TestScanStartActiveProjectGuard:
    def test_scan_start_no_project(self, repl):
        """cmd_scan_start rejects when no project is active."""
        repl.active_project = None
        cmd = ScanCommands(repl)
        cmd.cmd_scan_start("scan", [])
        printed = str(repl.console.print.call_args_list)
        assert "No active project" in printed

    def test_scan_resume_no_project(self, repl):
        """cmd_scan_resume rejects when no project is active."""
        repl.active_project = None
        cmd = ScanCommands(repl)
        cmd.cmd_scan_resume("scan", ["42"])
        printed = str(repl.console.print.call_args_list)
        assert "No active project" in printed


class TestInteractiveScanMintsMcpInfo:
    def test_interactive_scan_prints_mcp_info(self, repl):
        """Interactive scan mints a bearer token and prints connection info."""
        row = MagicMock(id=1, archived_at=None)
        repl.project_registry.resolve_by_name.return_value = row

        cmd = ScanCommands(repl)
        with (
            patch(
                "application.repl.commands.scan_commands.load_active_repos",
                return_value=[MagicMock()],
            ),
            patch(
                "application.repl.commands.scan_commands.mint_bearer_token",
                return_value="test-token-abc",
            ),
            patch("application.repl.commands.scan_commands.ConfigManager") as cm_cls,
        ):
            cfg = MagicMock()
            cfg.mcp.host = "127.0.0.1"
            cfg.mcp.port = 8765
            cm_cls.return_value.global_config = cfg

            cmd.cmd_scan_start("scan", [])

        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "mcp_url" in printed
        assert "mcp_bearer_token" in printed
        assert "test-token-abc" in printed


class TestDefaultInteractionMode:
    def test_scan_start_defaults_interactive(self, repl):
        """scan start with no mode flag defaults to interactive."""
        row = MagicMock(id=1, archived_at=None)
        repl.project_registry.resolve_by_name.return_value = row

        cmd = ScanCommands(repl)
        with (
            patch(
                "application.repl.commands.scan_commands.load_active_repos",
                return_value=[MagicMock()],
            ),
            patch.object(cmd, "_print_interactive_scan_info") as mint_fn,
        ):
            cmd.cmd_scan_start("scan", [])
            mint_fn.assert_called_once()

    def test_triage_start_defaults_interactive(self, repl):
        """triage start with no mode flag defaults to interactive."""
        repl.triage_readiness = MagicMock(enabled=True)
        row = MagicMock(id=1, archived_at=None)
        repl.project_registry.resolve_by_name.return_value = row

        cmd = TriageCommands(repl)
        with (
            patch(
                "application.repl.commands.triage_commands.ensure_image",
                return_value=False,
            ),
            patch(
                "application.repl.commands.triage_commands.image_ready",
                return_value=True,
            ),
            patch(
                "application.repl.commands.triage_commands.ensure_containers",
                return_value=False,
            ),
            patch(
                "application.repl.commands.triage_commands.resolve_triage_config",
                return_value=MagicMock(
                    provider_name="claude", base_url="", model="sonnet"
                ),
            ),
            patch(
                "application.repl.commands.triage_commands.containers_running",
                return_value=True,
            ),
            patch(
                "application.repl.commands.triage_commands.load_active_repos",
                return_value=[],
            ),
            patch(
                "application.repl.commands.triage_commands.create_triage_service"
            ) as svc_mock,
            patch(
                "application.repl.commands.triage_commands.mint_bearer_token",
                return_value="triage-token-xyz",
            ),
            patch("application.repl.commands.triage_commands.ConfigManager") as cm_cls,
        ):
            cfg = MagicMock()
            cfg.mcp.host = "127.0.0.1"
            cfg.mcp.port = 8765
            cm_cls.return_value.global_config = cfg

            from concurrent.futures import Future

            handle = MagicMock()
            handle.scan_run_id = 99
            future: Future[dict] = Future()
            future.set_result(
                {
                    "sessions_run": 1,
                    "success": 1,
                    "failed": 0,
                    "incomplete": 0,
                }
            )
            handle.result = future
            svc_mock.return_value.start_triage.return_value = handle

            cmd.cmd_triage_start("triage", [])

        printed = " ".join(str(c) for c in repl.console.print.call_args_list)
        assert "mcp_url" in printed
        assert "triage-token-xyz" in printed
