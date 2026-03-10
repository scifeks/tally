"""Tests for search results display logic in knowledge_commands.py.

No external services required — all tests use synthetic result dicts
and capture Rich table output via StringIO.
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Console

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.repl.commands.knowledge_commands import (  # noqa: E402
    _all_from_tool,
    _build_generic_table,
    _build_gitleaks_table,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LONG_PATH = "/very/long/path/to/src/main/java/com/example/auth/AuthService.java"


def _gitleaks_result(
    file_path: str = "/src/app.py",
    line_number: int = 42,
    risk_type: str = "generic-api-key",
    severity: str = "high",
    distance: float | None = None,
) -> dict[str, Any]:
    return {
        "document": (
            f"[gitleaks] Secret detected: {risk_type} in {file_path}:{line_number}"
        ),
        "metadata": {
            "tool": "gitleaks",
            "domain": "code",
            "severity": severity,
            "risk_type": risk_type,
            "file_path": file_path,
            "line_number": line_number,
            "type_secret": True,
        },
        "distance": distance,
    }


def _nmap_result(distance: float | None = None) -> dict[str, Any]:
    return {
        "document": "[nmap] Host 127.0.0.1 port 22 open ssh",
        "metadata": {
            "tool": "nmap",
            "domain": "network",
            "severity": "informational",
            "risk_type": "exposed_service",
            "type_exposure": True,
        },
        "distance": distance,
    }


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


# ---------------------------------------------------------------------------
# _all_from_tool
# ---------------------------------------------------------------------------


class TestAllFromTool:
    def test_empty_list_returns_false(self) -> None:
        assert _all_from_tool([], "gitleaks") is False

    def test_single_matching_result(self) -> None:
        assert _all_from_tool([_gitleaks_result()], "gitleaks") is True

    def test_multiple_matching_results(self) -> None:
        results = [_gitleaks_result(), _gitleaks_result(file_path="/other.py")]
        assert _all_from_tool(results, "gitleaks") is True

    def test_single_non_matching_result(self) -> None:
        assert _all_from_tool([_nmap_result()], "gitleaks") is False

    def test_mixed_tools_returns_false(self) -> None:
        results = [_gitleaks_result(), _nmap_result()]
        assert _all_from_tool(results, "gitleaks") is False

    def test_non_gitleaks_tool_name(self) -> None:
        assert _all_from_tool([_nmap_result()], "nmap") is True


# ---------------------------------------------------------------------------
# _build_gitleaks_table — column headers
# ---------------------------------------------------------------------------


class TestGitleaksTableHeaders:
    def test_has_file_path_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "File Path" in rendered

    def test_has_line_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Line" in rendered

    def test_has_tool_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Tool" in rendered

    def test_has_domain_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Domain" in rendered

    def test_has_type_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Type" in rendered

    def test_has_severity_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Severity" in rendered

    def test_has_risk_type_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Risk Type" in rendered

    def test_no_finding_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Finding" not in rendered

    def test_has_confidence_column(self) -> None:
        table = _build_gitleaks_table([_gitleaks_result()], is_semantic=False)
        rendered = _render(table)
        assert "Confidence" in rendered


# ---------------------------------------------------------------------------
# _build_gitleaks_table — file path not truncated
# ---------------------------------------------------------------------------


class TestGitleaksTableFilePath:
    def test_full_path_present(self) -> None:
        table = _build_gitleaks_table(
            [_gitleaks_result(file_path=_LONG_PATH)], is_semantic=False
        )
        rendered = _render(table)
        assert _LONG_PATH in rendered

    def test_short_path_present(self) -> None:
        table = _build_gitleaks_table(
            [_gitleaks_result(file_path="/src/app.py")], is_semantic=False
        )
        rendered = _render(table)
        assert "/src/app.py" in rendered


# ---------------------------------------------------------------------------
# _build_gitleaks_table — line number as integer
# ---------------------------------------------------------------------------


class TestGitleaksTableLineNumber:
    def test_integer_line_number_displayed(self) -> None:
        result = _gitleaks_result(line_number=99)
        table = _build_gitleaks_table([result], is_semantic=False)
        rendered = _render(table)
        assert "99" in rendered

    def test_line_number_not_displayed_as_float(self) -> None:
        result = _gitleaks_result(line_number=42)
        table = _build_gitleaks_table([result], is_semantic=False)
        rendered = _render(table)
        assert "42.0" not in rendered
        assert "42" in rendered

    def test_float_stored_line_number_renders_as_int(self) -> None:
        result = _gitleaks_result(line_number=7)
        result["metadata"]["line_number"] = 7.0  # simulate ChromaDB float storage
        table = _build_gitleaks_table([result], is_semantic=False)
        rendered = _render(table)
        assert "7.0" not in rendered
        assert "7" in rendered


# ---------------------------------------------------------------------------
# _build_gitleaks_table — risk type
# ---------------------------------------------------------------------------


class TestGitleaksTableRiskType:
    def test_risk_type_value_displayed(self) -> None:
        table = _build_gitleaks_table(
            [_gitleaks_result(risk_type="aws-access-token")], is_semantic=False
        )
        rendered = _render(table)
        assert "aws-access-token" in rendered


# ---------------------------------------------------------------------------
# _build_gitleaks_table — severity color coding
# ---------------------------------------------------------------------------


class TestGitleaksTableSeverity:
    def test_severity_value_rendered(self) -> None:
        table = _build_gitleaks_table(
            [_gitleaks_result(severity="high")], is_semantic=False
        )
        rendered = _render(table)
        assert "high" in rendered

    def test_critical_severity_uses_red_markup(self) -> None:
        from core.repl.commands.knowledge_commands import _color_severity

        markup = _color_severity("critical")
        assert "[red]" in markup
        assert "critical" in markup

    def test_informational_severity_uses_white_markup(self) -> None:
        from core.repl.commands.knowledge_commands import _color_severity

        markup = _color_severity("informational")
        assert "[white]" in markup

    def test_medium_severity_uses_yellow_markup(self) -> None:
        from core.repl.commands.knowledge_commands import _color_severity

        markup = _color_severity("medium")
        assert "[yellow]" in markup

    def test_low_severity_uses_blue_markup(self) -> None:
        from core.repl.commands.knowledge_commands import _color_severity

        markup = _color_severity("low")
        assert "[blue]" in markup


# ---------------------------------------------------------------------------
# _build_gitleaks_table — Confidence column
# ---------------------------------------------------------------------------


class TestGitleaksTableConfidence:
    def _result_with_confidence(self, confidence: str) -> dict[str, Any]:
        r = _gitleaks_result()
        r["metadata"]["confidence"] = confidence
        return r

    def test_confidence_displayed_in_gitleaks_table(self) -> None:
        result = self._result_with_confidence("confirmed")
        table = _build_gitleaks_table([result], is_semantic=False)
        rendered = _render(table)
        assert "confirmed" in rendered

    def test_missing_confidence_renders_empty_cell(self) -> None:
        result = _gitleaks_result()  # no confidence key in metadata
        result["metadata"].pop("confidence", None)
        table = _build_gitleaks_table([result], is_semantic=False)
        rendered = _render(table)
        # Table renders without error; Confidence column header still present
        assert "Confidence" in rendered


# ---------------------------------------------------------------------------
# _build_gitleaks_table — Relevance column
# ---------------------------------------------------------------------------


class TestGitleaksTableRelevance:
    def test_relevance_absent_for_metadata_only(self) -> None:
        results = [_gitleaks_result(distance=None)]
        table = _build_gitleaks_table(results, is_semantic=False)
        rendered = _render(table)
        assert "Relevance" not in rendered

    def test_relevance_present_for_semantic(self) -> None:
        results = [_gitleaks_result(distance=0.123)]
        table = _build_gitleaks_table(results, is_semantic=True)
        rendered = _render(table)
        assert "Relevance" in rendered

    def test_relevance_value_formatted_to_three_decimals(self) -> None:
        results = [_gitleaks_result(distance=0.456789)]
        table = _build_gitleaks_table(results, is_semantic=True)
        rendered = _render(table)
        assert "0.457" in rendered


# ---------------------------------------------------------------------------
# _build_generic_table — mixed tools use generic format
# ---------------------------------------------------------------------------


class TestGenericTable:
    def test_has_finding_column(self) -> None:
        results = [_gitleaks_result(), _nmap_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "Finding" in rendered

    def test_no_file_path_column(self) -> None:
        results = [_gitleaks_result(), _nmap_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "File Path" not in rendered

    def test_no_line_column(self) -> None:
        results = [_gitleaks_result(), _nmap_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        # "Line" also appears in "Finding" — check header row only
        # Both tools share columns, just verify Line column header absent
        assert "Line " not in rendered  # trailing space excludes "Finding"

    def test_relevance_absent_for_metadata_only(self) -> None:
        results = [_gitleaks_result(distance=None), _nmap_result(distance=None)]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "Relevance" not in rendered

    def test_relevance_present_for_semantic(self) -> None:
        results = [_gitleaks_result(distance=0.2), _nmap_result(distance=0.5)]
        table = _build_generic_table(results, is_semantic=True)
        rendered = _render(table)
        assert "Relevance" in rendered

    def test_both_tools_appear_in_rendered_output(self) -> None:
        results = [_gitleaks_result(), _nmap_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "gitleaks" in rendered
        assert "nmap" in rendered
