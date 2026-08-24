"""Unit tests for compute_triage_readiness."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from application.triage.readiness import compute_triage_readiness

_LOAD_PROVIDER = "application.triage.readiness.load_triage_provider"


class TestTriageReadiness:
    def test_disabled_provider_returns_disabled(self) -> None:
        with patch(_LOAD_PROVIDER, return_value=""):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="",
            )
        assert result.enabled is False
        assert result.reason == "Triage disabled in config"

    def test_missing_config_returns_disabled(self) -> None:
        with patch(_LOAD_PROVIDER, side_effect=FileNotFoundError):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="",
            )
        assert result.enabled is False
        assert result.reason == "Triage disabled in config"

    def test_docker_not_available_returns_disabled(self) -> None:
        with patch(_LOAD_PROVIDER, return_value="claude_code"):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=False,
                claude_api_key="",
            )
        assert result.enabled is False
        assert "Docker" in (result.reason or "")
        assert result.provider == "claude_code"

    def test_provider_and_docker_returns_enabled(self) -> None:
        with patch(_LOAD_PROVIDER, return_value="claude_code"):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="sk-ant-test",
            )
        assert result.enabled is True
        assert result.reason is None
        assert result.provider == "claude_code"
        assert result.backend_label == "Claude Code"

    def test_opencode_provider_enabled(self) -> None:
        with patch(_LOAD_PROVIDER, return_value="open_code"):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="",
            )
        assert result.enabled is True
        assert result.provider == "open_code"
        assert result.backend_label == "OpenCode"

    def test_opencode_without_docker_disabled(self) -> None:
        with patch(_LOAD_PROVIDER, return_value="open_code"):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=False,
                claude_api_key="",
            )
        assert result.enabled is False
        assert "Docker" in (result.reason or "")

    def test_claude_code_no_api_key_returns_disabled(self) -> None:
        with (
            patch(_LOAD_PROVIDER, return_value="claude_code"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="",
            )
        assert result.enabled is False
        assert "API key" in (result.reason or "")
        assert "MCP" in (result.reason or "")

    def test_claude_code_with_config_api_key_enabled(self) -> None:
        with patch(_LOAD_PROVIDER, return_value="claude_code"):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="sk-ant-test",
            )
        assert result.enabled is True

    def test_claude_code_with_env_api_key_enabled(self) -> None:
        with (
            patch(_LOAD_PROVIDER, return_value="claude_code"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-env"}),
        ):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="",
            )
        assert result.enabled is True

    def test_open_code_ignores_api_key(self) -> None:
        with patch(_LOAD_PROVIDER, return_value="open_code"):
            result = compute_triage_readiness(
                base_path=Path("/unused"),
                docker_available=True,
                claude_api_key="",
            )
        assert result.enabled is True
