"""Tests for triage audit trail constants."""

from __future__ import annotations

from domain.triage.constants import TRIAGE_MODES, TRIAGE_PROVIDERS


class TestTriageConstants:
    def test_triage_providers_is_frozen(self) -> None:
        assert isinstance(TRIAGE_PROVIDERS, frozenset)

    def test_triage_providers_contains_expected_values(self) -> None:
        assert TRIAGE_PROVIDERS == {"anthropic", "opencode", "openai", "mcp"}

    def test_triage_modes_is_frozen(self) -> None:
        assert isinstance(TRIAGE_MODES, frozenset)

    def test_triage_modes_contains_expected_values(self) -> None:
        assert TRIAGE_MODES == {"mcp_triage", "auto_triage", "manual"}
