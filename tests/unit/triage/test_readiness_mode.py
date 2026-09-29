"""Unit tests for triage mode computation in compute_triage_readiness."""

from __future__ import annotations

from application.triage.readiness import compute_triage_readiness


class TestTriageModeComputation:
    def test_no_provider_returns_disabled(self) -> None:
        r = compute_triage_readiness(
            provider="",
            docker_available=True,
            api_key="",
        )
        assert r.enabled is False
        assert r.triage_mode is None

    def test_claude_with_key_returns_auto(self) -> None:
        r = compute_triage_readiness(
            provider="claude",
            docker_available=True,
            api_key="sk-ant-xxx",
        )
        assert r.enabled is True
        assert r.triage_mode == "auto"

    def test_claude_without_key_returns_mcp(self) -> None:
        r = compute_triage_readiness(
            provider="claude",
            docker_available=False,
            api_key="",
        )
        assert r.enabled is True
        assert r.triage_mode == "mcp"

    def test_claude_mcp_mode_no_docker_still_enabled(self) -> None:
        r = compute_triage_readiness(
            provider="claude",
            docker_available=False,
            api_key="",
        )
        assert r.enabled is True

    def test_claude_auto_mode_no_docker_disabled(self) -> None:
        r = compute_triage_readiness(
            provider="claude",
            docker_available=False,
            api_key="sk-ant-xxx",
        )
        assert r.enabled is False
        assert r.triage_mode == "auto"

    def test_openai_with_key_returns_auto(self) -> None:
        r = compute_triage_readiness(
            provider="openai",
            docker_available=True,
            api_key="sk-xxx",
        )
        assert r.enabled is True
        assert r.triage_mode == "auto"

    def test_openai_without_key_returns_mcp(self) -> None:
        r = compute_triage_readiness(
            provider="openai",
            docker_available=False,
            api_key="",
        )
        assert r.enabled is True
        assert r.triage_mode == "mcp"

    def test_ollama_returns_auto(self) -> None:
        r = compute_triage_readiness(
            provider="ollama",
            docker_available=True,
            api_key="",
        )
        assert r.enabled is True
        assert r.triage_mode == "auto"

    def test_opencode_returns_auto(self) -> None:
        r = compute_triage_readiness(
            provider="opencode",
            docker_available=True,
            api_key="",
        )
        assert r.enabled is True
        assert r.triage_mode == "auto"
