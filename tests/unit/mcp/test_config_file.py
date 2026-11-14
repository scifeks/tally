"""Tests for MCP show-config output."""

from __future__ import annotations

import json

from application.mcp.config_file import format_show_config


class TestFormatShowConfig:
    def test_json_snippet_is_valid_json(self) -> None:
        result = format_show_config("127.0.0.1", 8765, "test-token-abc")
        parsed = json.loads(result.json_snippet)
        tally = parsed["tally"]
        assert tally["type"] == "http"
        assert tally["url"] == "http://127.0.0.1:8765/mcp"
        auth = tally["headers"]["Authorization"]
        assert auth == "Bearer test-token-abc"

    def test_cli_command_contains_scope_user(self) -> None:
        result = format_show_config("127.0.0.1", 8765, "tok")
        assert "--scope user" in result.cli_command

    def test_cli_command_contains_token(self) -> None:
        result = format_show_config("127.0.0.1", 8765, "my-secret")
        assert "my-secret" in result.cli_command

    def test_custom_port(self) -> None:
        result = format_show_config("127.0.0.1", 9000, "tok")
        parsed = json.loads(result.json_snippet)
        assert "9000" in parsed["tally"]["url"]

    def test_no_headers_helper_in_output(self) -> None:
        result = format_show_config("127.0.0.1", 8765, "tok")
        assert "headersHelper" not in result.json_snippet
        assert "headersHelper" not in result.cli_command
