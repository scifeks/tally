"""Unit tests for render_finding_type."""

from __future__ import annotations

from application.repl.commands.findings_table import render_finding_type


class TestRenderFindingType:
    def test_single_element_list_renders_plain(self) -> None:
        assert render_finding_type({"finding_type": ["informational"]}) == (
            "informational"
        )

    def test_two_element_list_renders_joined(self) -> None:
        result = render_finding_type({"finding_type": ["vulnerability", "dependency"]})
        assert result == "vulnerability, dependency"

    def test_missing_finding_type_falls_back_to_extract_types(self) -> None:
        # No finding_type and no type_* booleans → empty string
        assert render_finding_type({}) == ""

    def test_string_finding_type_passes_through(self) -> None:
        assert render_finding_type({"finding_type": "secret"}) == "secret"

    def test_empty_string_finding_type_falls_back(self) -> None:
        # Empty string → falls back to _extract_types, no flags → ""
        assert render_finding_type({"finding_type": ""}) == ""
