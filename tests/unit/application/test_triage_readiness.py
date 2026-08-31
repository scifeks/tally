"""Unit tests for compute_triage_readiness reason and label output."""

from __future__ import annotations

from application.triage.readiness import compute_triage_readiness


class TestTriageReadiness:
    def test_no_provider_reason_and_passthrough(self) -> None:
        result = compute_triage_readiness(
            provider="",
            docker_available=True,
            api_key="",
        )
        assert result.enabled is False
        assert result.reason == "Triage disabled in config"
        assert result.provider == ""
        assert result.backend_label is None

    def test_local_provider_without_docker_reason(self) -> None:
        result = compute_triage_readiness(
            provider="open_code",
            docker_available=False,
            api_key="",
        )
        assert result.enabled is False
        assert result.reason == "Docker is not installed or not running"
        assert result.provider == "open_code"

    def test_local_provider_ready(self) -> None:
        result = compute_triage_readiness(
            provider="open_code",
            docker_available=True,
            api_key="",
        )
        assert result.enabled is True
        assert result.reason is None
        assert result.provider == "open_code"
        assert result.backend_label == "OpenCode"

    def test_frontier_with_key_and_docker_ready(self) -> None:
        result = compute_triage_readiness(
            provider="claude_code",
            docker_available=True,
            api_key="sk-ant-test",
        )
        assert result.enabled is True
        assert result.reason is None
        assert result.backend_label == "Claude Code"

    def test_frontier_with_key_but_no_docker_reason(self) -> None:
        result = compute_triage_readiness(
            provider="claude_code",
            docker_available=False,
            api_key="sk-ant-test",
        )
        assert result.enabled is False
        assert result.reason == "Docker is not installed or not running"

    def test_frontier_without_key_enabled_with_no_reason(self) -> None:
        result = compute_triage_readiness(
            provider="claude_code",
            docker_available=True,
            api_key="",
        )
        assert result.enabled is True
        assert result.reason is None
