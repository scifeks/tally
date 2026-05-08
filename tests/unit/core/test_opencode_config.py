"""Unit tests for OpenCodeConfig schema."""

from __future__ import annotations

from core.config.schemas import GlobalConfig, OpenCodeConfig


class TestOpenCodeConfigDefaults:
    def test_defaults_to_empty_strings(self) -> None:
        cfg = OpenCodeConfig()
        assert cfg.api_key == ""
        assert cfg.api_provider == ""

    def test_explicit_values(self) -> None:
        cfg = OpenCodeConfig(
            api_key="sk-test-123",
            api_provider="http://localhost:11434/v1",
        )
        assert cfg.api_key == "sk-test-123"
        assert cfg.api_provider == "http://localhost:11434/v1"


class TestOpenCodeConfigInGlobalConfig:
    def test_global_config_defaults_to_none(self) -> None:
        cfg = GlobalConfig()
        assert cfg.opencode is None

    def test_global_config_accepts_opencode_block(self) -> None:
        cfg = GlobalConfig(
            opencode=OpenCodeConfig(api_key="key", api_provider="http://x")
        )
        assert cfg.opencode is not None
        assert cfg.opencode.api_key == "key"
        assert cfg.opencode.api_provider == "http://x"

    def test_global_config_ignores_extra_opencode_fields(self) -> None:
        cfg = GlobalConfig(opencode=OpenCodeConfig(api_key=""))
        assert cfg.opencode is not None
        assert cfg.opencode.api_key == ""
