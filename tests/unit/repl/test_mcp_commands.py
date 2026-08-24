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
        repl.console.print.assert_called_with("Usage: mcp token <create|list|revoke>")

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
        repl.console.print.assert_called_with("Usage: mcp token <create|list|revoke>")


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
