"""Tests for MCP show-config output."""

from __future__ import annotations

import json

from application.mcp.config_file import format_show_config


class TestFormatShowConfig:
    def test_json_snippet_is_valid_json(self) -> None:
        result = format_show_config("127.0.0.1", 8765)
        parsed = json.loads(result.json_snippet)
        tally = parsed["tally"]
        assert tally["type"] == "http"
        assert tally["url"] == "http://127.0.0.1:8765/mcp"
        auth = tally["headers"]["Authorization"]
        assert auth == "Bearer ${TALLY_MCP_TOKEN}"

    def test_cli_command_contains_scope_user(self) -> None:
        result = format_show_config("127.0.0.1", 8765)
        assert "--scope user" in result.cli_command

    def test_cli_command_contains_json_payload(self) -> None:
        result = format_show_config("127.0.0.1", 8765)
        assert '"type":"http"' in result.cli_command
        assert "http://127.0.0.1:8765/mcp" in result.cli_command

    def test_custom_port(self) -> None:
        result = format_show_config("127.0.0.1", 9000)
        parsed = json.loads(result.json_snippet)
        assert "9000" in parsed["tally"]["url"]

    def test_no_literal_token_in_output(self) -> None:
        result = format_show_config("127.0.0.1", 8765)
        assert "${TALLY_MCP_TOKEN}" in result.json_snippet
        assert "${TALLY_MCP_TOKEN}" in result.cli_command
