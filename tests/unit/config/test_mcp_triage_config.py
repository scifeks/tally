"""McpTriageConfig schema validation."""

from __future__ import annotations

from core.config.schemas.mcp_triage_config import McpTriageConfig


class TestMcpTriageConfig:
    def test_defaults(self) -> None:
        cfg = McpTriageConfig()
        assert cfg.max_concurrent_agents == 3

    def test_from_dict(self) -> None:
        cfg = McpTriageConfig(**{"max_concurrent_agents": 5})
        assert cfg.max_concurrent_agents == 5

    def test_extra_ignored(self) -> None:
        cfg = McpTriageConfig(**{"max_concurrent_agents": 2, "x": 1})
        assert cfg.max_concurrent_agents == 2
