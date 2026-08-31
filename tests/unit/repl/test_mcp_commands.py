"""Tests for REPL MCP token commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.mcp_commands import McpCommands


def _mock_repl() -> MagicMock:
    """Create a mock REPL with necessary attributes."""
    repl = MagicMock()
    repl.base_path = "/tmp/tally"
    repl.project_registry._repo.db_path = "/tmp/tally/tally.db"
    repl.console = MagicMock()
    return repl


class TestCmdMcp:
    def test_no_args_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", [])
        output = repl.console.print.call_args[0][0]
        assert "Usage: mcp" in output

    def test_token_no_subcommand_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", ["token"])
        repl.console.print.assert_called_with("Usage: mcp token <create|list|revoke>")

    def test_token_create_without_name_calls_create_token_with_default(
        self,
    ) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_create_token") as mock_create:
            cmd.cmd_mcp("mcp", ["token", "create"])
            mock_create.assert_called_once_with("default")

    def test_token_create_with_name_calls_create_token(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_create_token") as mock_create:
            cmd.cmd_mcp("mcp", ["token", "create", "mytoken"])
            mock_create.assert_called_once_with("mytoken")

    def test_token_list_calls_list_tokens(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_list_tokens") as mock_list:
            cmd.cmd_mcp("mcp", ["token", "list"])
            mock_list.assert_called_once()

    def test_token_revoke_without_name_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", ["token", "revoke"])
        repl.console.print.assert_called_with("Usage: mcp token revoke <name>")

    def test_token_revoke_with_name_calls_revoke_token(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_revoke_token") as mock_revoke:
            cmd.cmd_mcp("mcp", ["token", "revoke", "mytoken"])
            mock_revoke.assert_called_once_with("mytoken")

    def test_token_unknown_subcommand_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", ["token", "unknown"])
        repl.console.print.assert_called_with("Usage: mcp token <create|list|revoke>")

    def test_invalid_main_command_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", ["invalid"])
        output = repl.console.print.call_args[0][0]
        assert "Usage: mcp" in output

    def test_serve_no_args_shows_submenu(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_serve_submenu") as mock_submenu:
            cmd.cmd_mcp("mcp", ["serve"])
            mock_submenu.assert_called_once()

    def test_serve_start_dispatches_to_serve_start(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_serve_start") as mock_start:
            cmd.cmd_mcp("mcp", ["serve", "start"])
            mock_start.assert_called_once()

    def test_serve_stop_dispatches_to_serve_stop(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_serve_stop") as mock_stop:
            cmd.cmd_mcp("mcp", ["serve", "stop"])
            mock_stop.assert_called_once()

    def test_serve_restart_dispatches_to_serve_restart(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_serve_restart") as mock_restart:
            cmd.cmd_mcp("mcp", ["serve", "restart"])
            mock_restart.assert_called_once()

    def test_serve_status_dispatches_to_serve_status(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_serve_status") as mock_status:
            cmd.cmd_mcp("mcp", ["serve", "status"])
            mock_status.assert_called_once()

    def test_serve_unknown_action_shows_submenu(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_serve_submenu") as mock_submenu:
            cmd.cmd_mcp("mcp", ["serve", "bogus"])
            mock_submenu.assert_called_once()

    def test_triage_prepare_without_run_id_passes_none(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_triage_prepare") as mock_prepare:
            cmd.cmd_mcp("mcp", ["triage", "prepare"])
            mock_prepare.assert_called_once_with(None)

    def test_triage_prepare_with_run_id_parses_int(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch.object(cmd, "_triage_prepare") as mock_prepare:
            cmd.cmd_mcp("mcp", ["triage", "prepare", "42"])
            mock_prepare.assert_called_once_with(42)

    def test_triage_no_args_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", ["triage"])
        output = repl.console.print.call_args[0][0]
        assert "Usage: mcp triage prepare" in output

    def test_triage_unknown_action_prints_usage(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        cmd.cmd_mcp("mcp", ["triage", "bogus"])
        output = repl.console.print.call_args[0][0]
        assert "Usage: mcp triage prepare" in output


class TestCreateToken:
    def test_creates_token_successfully(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_repo = MagicMock()
        with (
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository",
                return_value=mock_repo,
            ),
            patch(
                "application.repl.commands.mcp_commands.secrets.token_urlsafe"
            ) as mock_token,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=True,
            ),
            patch(
                "application.repl.commands.mcp_commands.get_encryption_key"
            ) as mock_get_key,
            patch(
                "application.repl.commands.mcp_commands.encrypt_value"
            ) as mock_encrypt,
        ):
            mock_token.return_value = "generated_token"
            mock_get_key.return_value = b"test_key"
            mock_encrypt.return_value = "encrypted_token"

            cmd._create_token("mytoken")

            mock_repo.create.assert_called_once_with("mytoken", "encrypted_token")
            assert repl.console.print.call_count >= 1

    def test_creates_key_file_if_missing(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_repo = MagicMock()
        with (
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository",
                return_value=mock_repo,
            ),
            patch(
                "application.repl.commands.mcp_commands.secrets.token_urlsafe"
            ) as mock_token,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=False,
            ),
            patch(
                "application.repl.commands.mcp_commands.create_key_file"
            ) as mock_create_key,
            patch(
                "application.repl.commands.mcp_commands.encrypt_value"
            ) as mock_encrypt,
        ):
            mock_token.return_value = "generated_token"
            mock_create_key.return_value = b"test_key"
            mock_encrypt.return_value = "encrypted_token"

            cmd._create_token("newtoken")

            assert mock_create_key.called
            mock_repo.create.assert_called_once()

    def test_handles_integrity_error(self) -> None:
        import sqlite3

        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_repo = MagicMock()
        mock_repo.create.side_effect = sqlite3.IntegrityError("UNIQUE constraint")
        with (
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository",
                return_value=mock_repo,
            ),
            patch(
                "application.repl.commands.mcp_commands.secrets.token_urlsafe",
                return_value="token",
            ),
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=True,
            ),
            patch("application.repl.commands.mcp_commands.get_encryption_key"),
            patch(
                "application.repl.commands.mcp_commands.encrypt_value",
                return_value="encrypted",
            ),
        ):
            cmd._create_token("duplicate")
            # Should print error but not crash
            assert repl.console.print.called

    def test_handles_generic_exception(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            side_effect=RuntimeError("DB error"),
        ):
            cmd._create_token("fail")
            repl.console.print.assert_called()
            call_args = repl.console.print.call_args[0][0]
            assert "Error creating token" in call_args


class TestListTokens:
    def test_lists_tokens_successfully(self) -> None:
        from application.ports.mcp_token_repository import McpTokenRow

        repl = _mock_repl()
        cmd = McpCommands(repl)
        tokens = [
            McpTokenRow(id=1, name="token1", created_at="2026-01-01T00:00:00Z"),
            McpTokenRow(id=2, name="token2", created_at="2026-01-02T00:00:00Z"),
        ]
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = tokens
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            return_value=mock_repo,
        ):
            cmd._list_tokens()
            assert repl.console.print.called

    def test_shows_message_when_no_tokens(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = []
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            return_value=mock_repo,
        ):
            cmd._list_tokens()
            repl.console.print.assert_called_with(
                "[yellow]No MCP tokens found.[/yellow]"
            )

    def test_handles_exception(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            side_effect=RuntimeError("DB error"),
        ):
            cmd._list_tokens()
            repl.console.print.assert_called()
            call_args = repl.console.print.call_args[0][0]
            assert "Error listing tokens" in call_args


class TestRevokeToken:
    def test_revokes_token_successfully(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_repo = MagicMock()
        mock_repo.revoke.return_value = True
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            return_value=mock_repo,
        ):
            cmd._revoke_token("mytoken")
            repl.console.print.assert_called_with(
                "[green]Token revoked:[/green] mytoken"
            )

    def test_shows_not_found_when_token_missing(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_repo = MagicMock()
        mock_repo.revoke.return_value = False
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            return_value=mock_repo,
        ):
            cmd._revoke_token("missing")
            repl.console.print.assert_called_with(
                "[yellow]Token not found:[/yellow] missing"
            )

    def test_handles_exception(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch(
            "application.repl.commands.mcp_commands.McpTokenRepository",
            side_effect=RuntimeError("DB error"),
        ):
            cmd._revoke_token("fail")
            repl.console.print.assert_called()
            call_args = repl.console.print.call_args[0][0]
            assert "Error revoking token" in call_args


class TestServeStart:
    def test_no_projects_configured_prints_error(self) -> None:
        repl = _mock_repl()
        repl.project_registry.list_active.return_value = []
        cmd = McpCommands(repl)
        with patch(
            "application.repl.commands.mcp_commands.ConfigManager"
        ) as mock_config_cls:
            mock_config_cls.return_value.global_config.mcp.host = "http://127.0.0.1"
            mock_config_cls.return_value.global_config.mcp.port = 8765
            cmd._serve_start()
        repl.console.print.assert_called_with(
            "[red]No projects configured.[/red] Create a project first."
        )

    def test_no_key_file_prints_error(self) -> None:
        repl = _mock_repl()
        repl.project_registry.list_active.return_value = ["proj1"]
        cmd = McpCommands(repl)
        with (
            patch(
                "application.repl.commands.mcp_commands.ConfigManager"
            ) as mock_config_cls,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=False,
            ),
        ):
            mock_config_cls.return_value.global_config.mcp.host = "http://127.0.0.1"
            mock_config_cls.return_value.global_config.mcp.port = 8765
            cmd._serve_start()
        repl.console.print.assert_called_with(
            "[red]No MCP tokens found.[/red] Run 'mcp token create <name>' first."
        )

    def test_no_tokens_prints_error(self) -> None:
        repl = _mock_repl()
        repl.project_registry.list_active.return_value = ["proj1"]
        cmd = McpCommands(repl)
        with (
            patch(
                "application.repl.commands.mcp_commands.ConfigManager"
            ) as mock_config_cls,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=True,
            ),
            patch(
                "application.repl.commands.mcp_commands.get_encryption_key",
                return_value=b"key",
            ),
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository"
            ) as mock_repo_cls,
        ):
            mock_config_cls.return_value.global_config.mcp.host = "http://127.0.0.1"
            mock_config_cls.return_value.global_config.mcp.port = 8765
            mock_repo_cls.return_value.list_all.return_value = []
            cmd._serve_start()
        repl.console.print.assert_called_with(
            "[red]No MCP tokens found.[/red] Run 'mcp token create <name>' first."
        )

    def test_creates_mcp_json_when_missing(self) -> None:
        repl = _mock_repl()
        repl.project_registry.list_active.return_value = ["proj1"]
        cmd = McpCommands(repl)
        handle = MagicMock(host="127.0.0.1", port=8765)
        with (
            patch(
                "application.repl.commands.mcp_commands.ConfigManager"
            ) as mock_config_cls,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                side_effect=[True, False],
            ),
            patch(
                "application.repl.commands.mcp_commands.get_encryption_key",
                return_value=b"key",
            ),
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository"
            ) as mock_repo_cls,
            patch(
                "application.repl.commands.mcp_commands.write_mcp_json"
            ) as mock_write_json,
            patch(
                "application.mcp.lifecycle.start_mcp_server_managed",
                return_value=handle,
            ),
        ):
            mock_config_cls.return_value.global_config.mcp.host = "http://127.0.0.1"
            mock_config_cls.return_value.global_config.mcp.port = 8765
            mock_repo_cls.return_value.list_all.return_value = ["tok1"]
            cmd._serve_start()

        mock_write_json.assert_called_once()

    def test_starts_server_and_strips_http_prefix_from_host(self) -> None:
        repl = _mock_repl()
        repl.project_registry.list_active.return_value = ["proj1"]
        cmd = McpCommands(repl)
        handle = MagicMock(host="127.0.0.1", port=8765)
        with (
            patch(
                "application.repl.commands.mcp_commands.ConfigManager"
            ) as mock_config_cls,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=True,
            ),
            patch(
                "application.repl.commands.mcp_commands.get_encryption_key",
                return_value=b"key",
            ),
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository"
            ) as mock_repo_cls,
            patch(
                "application.mcp.lifecycle.start_mcp_server_managed",
                return_value=handle,
            ) as mock_start,
        ):
            mock_config_cls.return_value.global_config.mcp.host = "http://127.0.0.1"
            mock_config_cls.return_value.global_config.mcp.port = 8765
            mock_repo_cls.return_value.list_all.return_value = ["tok1"]
            cmd._serve_start()

        mock_start.assert_called_once()
        _, kwargs = mock_start.call_args
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8765
        assert kwargs["source"] == "repl"
        repl.console.print.assert_called_with(
            "[green]MCP server started on 127.0.0.1:8765[/green]"
        )

    def test_already_running_prints_runtime_error_message(self) -> None:
        repl = _mock_repl()
        repl.project_registry.list_active.return_value = ["proj1"]
        cmd = McpCommands(repl)
        with (
            patch(
                "application.repl.commands.mcp_commands.ConfigManager"
            ) as mock_config_cls,
            patch(
                "application.repl.commands.mcp_commands.Path.exists",
                return_value=True,
            ),
            patch(
                "application.repl.commands.mcp_commands.get_encryption_key",
                return_value=b"key",
            ),
            patch(
                "application.repl.commands.mcp_commands.McpTokenRepository"
            ) as mock_repo_cls,
            patch(
                "application.mcp.lifecycle.start_mcp_server_managed",
                side_effect=RuntimeError("MCP server already running on port 8765"),
            ),
        ):
            mock_config_cls.return_value.global_config.mcp.host = "http://127.0.0.1"
            mock_config_cls.return_value.global_config.mcp.port = 8765
            mock_repo_cls.return_value.list_all.return_value = ["tok1"]
            cmd._serve_start()

        repl.console.print.assert_called_with(
            "[red]MCP server already running on port 8765[/red]"
        )


class TestServeStop:
    def test_prints_success_when_stopped(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch("application.mcp.lifecycle.stop_mcp_server", return_value=True):
            cmd._serve_stop()
        repl.console.print.assert_called_with("[green]MCP server stopped[/green]")

    def test_prints_warning_when_nothing_to_stop(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        with patch("application.mcp.lifecycle.stop_mcp_server", return_value=False):
            cmd._serve_stop()
        repl.console.print.assert_called_with("[yellow]No active MCP server[/yellow]")


class TestServeRestart:
    def test_stops_then_starts(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        calls: list[str] = []
        with (
            patch.object(cmd, "_serve_stop", side_effect=lambda: calls.append("stop")),
            patch.object(
                cmd, "_serve_start", side_effect=lambda: calls.append("start")
            ),
            patch("time.sleep"),
        ):
            cmd._serve_restart()
        assert calls == ["stop", "start"]


class TestServeStatus:
    def test_prints_not_running_when_no_handle(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        with patch(
            "application.mcp.registry.get_mcp_server_registry",
            return_value=mock_registry,
        ):
            cmd._serve_status()
        repl.console.print.assert_called_with("[dim]MCP server: not running[/dim]")

    def test_prints_running_status_with_handle_details(self) -> None:
        repl = _mock_repl()
        cmd = McpCommands(repl)
        handle = MagicMock(host="127.0.0.1", port=8765, source="repl")
        mock_registry = MagicMock()
        mock_registry.get.return_value = handle
        with patch(
            "application.mcp.registry.get_mcp_server_registry",
            return_value=mock_registry,
        ):
            cmd._serve_status()
        repl.console.print.assert_called_with(
            "[green]MCP server: running on 127.0.0.1:8765 (source: repl)[/green]"
        )


class TestTriagePrepare:
    def test_no_active_project_prints_error(self) -> None:
        repl = _mock_repl()
        repl.active_project = None
        cmd = McpCommands(repl)
        cmd._triage_prepare(None)
        repl.console.print.assert_called_with(
            "[red]No active project.[/red] Run 'project switch <name>' first."
        )

    def test_project_not_found_prints_error(self) -> None:
        repl = _mock_repl()
        repl.active_project = "myproject"
        repl.project_registry.resolve_by_name.return_value = None
        cmd = McpCommands(repl)
        cmd._triage_prepare(None)
        repl.console.print.assert_called_with("[red]Active project not found.[/red]")

    def test_archived_project_prints_error(self) -> None:
        repl = _mock_repl()
        repl.active_project = "myproject"
        row = MagicMock(archived_at="2026-01-01T00:00:00Z")
        repl.project_registry.resolve_by_name.return_value = row
        cmd = McpCommands(repl)
        cmd._triage_prepare(None)
        repl.console.print.assert_called_with("[red]Active project not found.[/red]")

    def test_no_run_id_and_no_runs_prints_error(self) -> None:
        repl = _mock_repl()
        repl.active_project = "myproject"
        row = MagicMock(archived_at=None, path="/fake/project")
        repl.project_registry.resolve_by_name.return_value = row
        cmd = McpCommands(repl)
        with (
            patch("infrastructure.store.connection.ConnectionFactory"),
            patch(
                "infrastructure.store.repositories.runs.RunRepository"
            ) as mock_run_repo_cls,
        ):
            mock_run_repo_cls.return_value.latest_run_id.return_value = None
            cmd._triage_prepare(None)
        repl.console.print.assert_called_with("[red]No scan runs found[/red]")

    def test_creates_batches_for_latest_run_when_no_run_id_given(self) -> None:
        repl = _mock_repl()
        repl.active_project = "myproject"
        row = MagicMock(archived_at=None, path="/fake/project")
        repl.project_registry.resolve_by_name.return_value = row
        cmd = McpCommands(repl)
        with (
            patch("infrastructure.store.connection.ConnectionFactory"),
            patch(
                "infrastructure.store.repositories.runs.RunRepository"
            ) as mock_run_repo_cls,
            patch("infrastructure.store.repositories.triage.TriageBatchRepository"),
            patch(
                "application.triage.batch_creator.create_triage_batches",
                return_value=[(1, 3), (2, 2)],
            ) as mock_create_batches,
        ):
            mock_run_repo_cls.return_value.latest_run_id.return_value = 7
            cmd._triage_prepare(None)

        _, kwargs = mock_create_batches.call_args
        assert kwargs["run_id"] == 7
        assert kwargs["max_findings_per_batch"] == 4
        repl.console.print.assert_called_with(
            "[green]Created 2 batches (5 findings) for run 7[/green]"
        )

    def test_uses_explicit_run_id_without_querying_latest(self) -> None:
        repl = _mock_repl()
        repl.active_project = "myproject"
        row = MagicMock(archived_at=None, path="/fake/project")
        repl.project_registry.resolve_by_name.return_value = row
        cmd = McpCommands(repl)
        with (
            patch("infrastructure.store.connection.ConnectionFactory"),
            patch(
                "infrastructure.store.repositories.runs.RunRepository"
            ) as mock_run_repo_cls,
            patch("infrastructure.store.repositories.triage.TriageBatchRepository"),
            patch(
                "application.triage.batch_creator.create_triage_batches",
                return_value=[],
            ) as mock_create_batches,
        ):
            cmd._triage_prepare(99)

        mock_run_repo_cls.return_value.latest_run_id.assert_not_called()
        _, kwargs = mock_create_batches.call_args
        assert kwargs["run_id"] == 99
