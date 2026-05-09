"""Unit tests for credential resolution logic."""

from __future__ import annotations

from application.triage.credentials import (
    ClaudeAuthMode,
    ClaudeCredentials,
    OpenCodeCredentials,
    resolve_claude_credentials,
    resolve_opencode_credentials,
)
from core.config.schemas import ClaudeConfig, OpenCodeConfig


class TestResolveClaude:
    def test_api_key_present_selects_api_key_mode(self) -> None:
        cfg = ClaudeConfig(api_key="sk-ant-xxx")
        result = resolve_claude_credentials(cfg)
        assert result == ClaudeCredentials(
            mode=ClaudeAuthMode.API_KEY,
            api_key="sk-ant-xxx",
        )

    def test_empty_api_key_selects_oauth_mode(self) -> None:
        cfg = ClaudeConfig(api_key="")
        result = resolve_claude_credentials(cfg)
        assert result == ClaudeCredentials(
            mode=ClaudeAuthMode.OAUTH,
            api_key="",
        )

    def test_none_config_selects_oauth_mode(self) -> None:
        result = resolve_claude_credentials(None)
        assert result == ClaudeCredentials(
            mode=ClaudeAuthMode.OAUTH,
            api_key="",
        )

    def test_default_claude_config_selects_oauth(self) -> None:
        result = resolve_claude_credentials(ClaudeConfig())
        assert result.mode is ClaudeAuthMode.OAUTH


class TestResolveOpenCode:
    def test_config_with_values(self) -> None:
        cfg = OpenCodeConfig(
            api_key="test-key",
            api_provider="http://localhost:8080/v1",
        )
        result = resolve_opencode_credentials(cfg)
        assert result == OpenCodeCredentials(
            api_key="test-key",
            api_provider="http://localhost:8080/v1",
            model="",
        )

    def test_none_config_returns_empty_defaults(self) -> None:
        result = resolve_opencode_credentials(None)
        assert result == OpenCodeCredentials(
            api_key="",
            api_provider="",
            model="",
        )

    def test_default_opencode_config(self) -> None:
        result = resolve_opencode_credentials(OpenCodeConfig())
        assert result.api_key == ""
        assert result.api_provider == ""
        assert result.model == ""
