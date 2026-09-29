"""Tests for the burp poll REPL command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.burp_commands import (
    BurpCommands,
)
from domain.projects.entry import ProjectRow


def _project_row() -> ProjectRow:
    return ProjectRow(
        id=1,
        name="testproj",
        path="/tmp/tally_test/projects/testproj",
        created_at="2026-08-01T00:00:00Z",
    )


def _make_repl(
    *,
    active_project: str | None = "testproj",
    mcp_url: str = "http://127.0.0.1:9876/sse",
    poll_interval: int = 30,
) -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/tally_test"
    repl.project_registry.resolve_by_name.return_value = _project_row()

    burp_cfg = MagicMock()
    burp_cfg.mcp_url = mcp_url
    burp_cfg.poll_interval_seconds = poll_interval
    repl.config.global_config.burp = burp_cfg if mcp_url else None
    return repl


class TestCmdPollConstructsPoller:
    @patch("application.repl.commands.burp_commands.OrganizerPoller")
    @patch("application.repl.commands.burp_commands.BurpMcpClient")
    @patch("application.repl.commands.burp_commands.OrganizerStateRepository")
    @patch("application.repl.commands.burp_commands.McpIngestService")
    @patch("application.repl.commands.burp_commands.create_finding_repo")
    @patch("application.repl.commands.burp_commands.ConnectionFactory")
    @patch("application.repl.commands.burp_commands.create_llm_provider")
    def test_constructs_poller_with_correct_args(
        self,
        mock_llm,
        mock_conn_factory,
        mock_create_finding,
        mock_ingest_cls,
        mock_state_repo_cls,
        mock_mcp_client_cls,
        mock_poller_cls,
    ):
        mock_llm.side_effect = Exception("no LLM")
        mock_poller_cls.return_value.run.side_effect = KeyboardInterrupt
        mock_factory = MagicMock()
        mock_conn_factory.return_value = mock_factory

        repl = _make_repl()
        cmd = BurpCommands(repl)
        cmd.cmd_burp("burp", ["poll"])

        mock_poller_cls.assert_called_once()
        call_kwargs = mock_poller_cls.call_args.kwargs
        assert call_kwargs["project_id"] == 1
        assert call_kwargs["poll_interval"] == 30.0
        assert call_kwargs["note_enrichment"] is None
        mock_poller_cls.return_value.run.assert_called_once()


class TestCmdPollValidation:
    def test_prints_error_without_active_project(self):
        repl = _make_repl(active_project=None)
        cmd = BurpCommands(repl)
        cmd.cmd_burp("burp", ["poll"])
        repl.console.print.assert_called()
        msg = repl.console.print.call_args[0][0]
        assert "No active project" in msg

    def test_prints_error_without_burp_config(self):
        repl = _make_repl(mcp_url="")
        cmd = BurpCommands(repl)
        cmd.cmd_burp("burp", ["poll"])
        repl.console.print.assert_called()
        msg = repl.console.print.call_args[0][0]
        assert "not configured" in msg

    def test_prints_usage_without_subcommand(self):
        repl = _make_repl()
        cmd = BurpCommands(repl)
        cmd.cmd_burp("burp", [])
        repl.console.print.assert_called()
        msg = repl.console.print.call_args[0][0]
        assert "Usage" in msg
