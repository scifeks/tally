"""McpConfig schema validation."""

from __future__ import annotations

from core.config.schemas.mcp_config import McpConfig


class TestMcpConfig:
    def test_defaults(self) -> None:
        cfg = McpConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8765

    def test_custom_values(self) -> None:
        cfg = McpConfig(host="https://10.1.20.101", port=9000)
        assert cfg.host == "https://10.1.20.101"
        assert cfg.port == 9000

    def test_port_coerced_from_string(self) -> None:
        cfg = McpConfig(port="9000")  # type: ignore[arg-type]
        assert cfg.port == 9000
