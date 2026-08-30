"""Tests for .mcp.json builder."""

from __future__ import annotations

import json
from pathlib import Path

from application.mcp.config_file import build_mcp_json, write_mcp_json


class TestBuildMcpJson:
    def test_default_localhost(self) -> None:
        result = build_mcp_json("http://127.0.0.1", 8765)
        assert result == {
            "mcpServers": {
                "tally": {
                    "type": "sse",
                    "url": "http://127.0.0.1:8765/sse",
                }
            }
        }

    def test_https_host(self) -> None:
        result = build_mcp_json("https://10.1.20.101", 9000)
        tally = result["mcpServers"]["tally"]
        assert tally["url"] == "https://10.1.20.101:9000/sse"

    def test_host_with_trailing_slash_stripped(self) -> None:
        result = build_mcp_json("http://localhost/", 8765)
        tally = result["mcpServers"]["tally"]
        assert tally["url"] == "http://localhost:8765/sse"


class TestWriteMcpJson:
    def test_writes_file(self, tmp_path: Path) -> None:
        path = write_mcp_json(tmp_path, "http://127.0.0.1", 8765)
        assert path == tmp_path / ".mcp.json"
        assert path.exists()
        content = json.loads(path.read_text())
        assert content["mcpServers"]["tally"]["type"] == "sse"

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        existing = tmp_path / ".mcp.json"
        existing.write_text('{"custom": true}')
        path = write_mcp_json(tmp_path, "http://127.0.0.1", 8765)
        assert path == existing
        content = json.loads(path.read_text())
        assert "custom" in content
