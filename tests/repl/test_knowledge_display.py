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
    _build_osv_table,
    _build_semgrep_table,
    _build_zap_table,
    _render_finding_type,
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
    def test_no_finding_column(self) -> None:
        results = [_gitleaks_result(), _nmap_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "Finding" not in rendered

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


# ---------------------------------------------------------------------------
# _semgrep_result helper
# ---------------------------------------------------------------------------


def _semgrep_result(
    rule_id: str = "php.lang.security.injection.taint.sink",
    file_path: str = "/src/BookingController.php",
    line_start: int = 42,
    severity: str = "medium",
    cwe: str = "",
    owasp: str = "",
    distance: float | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "tool": "semgrep",
        "domain": "code",
        "severity": severity,
        "rule_id": rule_id,
        "file_path": file_path,
        "line_start": line_start,
        "line_end": line_start + 2,
        "type_vulnerability": True,
        "type_weakness": True,
    }
    if cwe:
        meta["cwe"] = cwe
    if owasp:
        meta["owasp"] = owasp
    return {
        "document": (
            f"[semgrep] [{severity.upper()}] {rule_id} in {file_path}:{line_start}"
        ),
        "metadata": meta,
        "distance": distance,
    }


# ---------------------------------------------------------------------------
# _build_semgrep_table — column headers
# ---------------------------------------------------------------------------


class TestSemgrepTableHeaders:
    def test_has_rule_id_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Rule ID" in rendered

    def test_has_location_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Location" in rendered

    def test_has_confidence_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Confidence" in rendered

    def test_confidence_value_displayed(self) -> None:
        result = _semgrep_result()
        result["metadata"]["confidence"] = "high"
        table = _build_semgrep_table([result], is_semantic=False)
        rendered = _render(table)
        assert "high" in rendered

    def test_missing_confidence_renders_empty_cell(self) -> None:
        result = _semgrep_result()
        result["metadata"].pop("confidence", None)
        table = _build_semgrep_table([result], is_semantic=False)
        rendered = _render(table)
        assert "Confidence" in rendered

    def test_has_cwe_owasp_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "CWE / OWASP" in rendered

    def test_no_severity_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Severity" not in rendered

    def test_no_risk_type_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Risk Type" not in rendered

    def test_no_finding_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Finding" not in rendered

    def test_no_file_path_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "File Path" not in rendered

    def test_no_line_column(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        assert "Line " not in rendered


# ---------------------------------------------------------------------------
# _build_semgrep_table — location formatting
# ---------------------------------------------------------------------------


class TestSemgrepTableLocation:
    def test_location_contains_file_path_and_line(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(file_path="/src/BookingController.php", line_start=42)],
            is_semantic=False,
        )
        rendered = _render(table)
        assert "/src/BookingController.php:42" in rendered

    def test_float_line_start_renders_as_int(self) -> None:
        result = _semgrep_result(line_start=7)
        result["metadata"]["line_start"] = 7.0  # simulate ChromaDB float storage
        table = _build_semgrep_table([result], is_semantic=False)
        rendered = _render(table)
        assert "7.0" not in rendered
        assert ":7" in rendered

    def test_missing_line_start_shows_path_only(self) -> None:
        result = _semgrep_result(file_path="/src/app.php")
        result["metadata"].pop("line_start")
        table = _build_semgrep_table([result], is_semantic=False)
        rendered = _render(table)
        assert "/src/app.php" in rendered


# ---------------------------------------------------------------------------
# _build_semgrep_table — CWE / OWASP column
# ---------------------------------------------------------------------------


class TestSemgrepTableCweOwasp:
    def test_both_cwe_and_owasp_combined(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(cwe="CWE-502", owasp="A8:2021")],
            is_semantic=False,
        )
        rendered = _render(table)
        assert "CWE-502" in rendered
        assert "A8:2021" in rendered

    def test_only_cwe_shows_cwe(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(cwe="CWE-502")],
            is_semantic=False,
        )
        rendered = _render(table)
        assert "CWE-502" in rendered
        assert "A8:2021" not in rendered

    def test_only_owasp_shows_owasp(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(owasp="A8:2021")],
            is_semantic=False,
        )
        rendered = _render(table)
        assert "A8:2021" in rendered
        # "CWE" appears in the column header; verify no CWE value (e.g. "CWE-")
        assert "CWE-" not in rendered

    def test_neither_cwe_nor_owasp_blank_cell(self) -> None:
        table = _build_semgrep_table([_semgrep_result()], is_semantic=False)
        rendered = _render(table)
        # Header still present even when all cells are blank
        assert "CWE / OWASP" in rendered


# ---------------------------------------------------------------------------
# _build_semgrep_table — Relevance column
# ---------------------------------------------------------------------------


class TestSemgrepTableRelevance:
    def test_relevance_absent_for_metadata_only(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(distance=None)], is_semantic=False
        )
        rendered = _render(table)
        assert "Relevance" not in rendered

    def test_relevance_present_for_semantic(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(distance=0.123)], is_semantic=True
        )
        rendered = _render(table)
        assert "Relevance" in rendered

    def test_relevance_value_formatted_to_three_decimals(self) -> None:
        table = _build_semgrep_table(
            [_semgrep_result(distance=0.456789)], is_semantic=True
        )
        rendered = _render(table)
        assert "0.457" in rendered


# ---------------------------------------------------------------------------
# _all_from_tool — semgrep
# ---------------------------------------------------------------------------


class TestAllFromToolSemgrep:
    def test_all_semgrep_returns_true(self) -> None:
        results = [_semgrep_result(), _semgrep_result(rule_id="other.rule")]
        assert _all_from_tool(results, "semgrep") is True

    def test_mixed_semgrep_and_nmap_returns_false(self) -> None:
        results = [_semgrep_result(), _nmap_result()]
        assert _all_from_tool(results, "semgrep") is False

    def test_single_semgrep_returns_true(self) -> None:
        assert _all_from_tool([_semgrep_result()], "semgrep") is True


# ---------------------------------------------------------------------------
# _render_finding_type
# ---------------------------------------------------------------------------


class TestRenderFindingType:
    def test_single_element_list_renders_plain(self) -> None:
        assert _render_finding_type({"finding_type": ["informational"]}) == (
            "informational"
        )

    def test_two_element_list_renders_joined(self) -> None:
        result = _render_finding_type({"finding_type": ["vulnerability", "dependency"]})
        assert result == "vulnerability, dependency"

    def test_missing_finding_type_falls_back_to_extract_types(self) -> None:
        # No finding_type and no type_* booleans → empty string
        assert _render_finding_type({}) == ""

    def test_string_finding_type_passes_through(self) -> None:
        assert _render_finding_type({"finding_type": "secret"}) == "secret"

    def test_empty_string_finding_type_falls_back(self) -> None:
        # Empty string → falls back to _extract_types, no flags → ""
        assert _render_finding_type({"finding_type": ""}) == ""


# ---------------------------------------------------------------------------
# _build_generic_table — nmap with finding_type list
# ---------------------------------------------------------------------------


def _sqlite_nmap_result(distance: float | None = None) -> dict[str, Any]:
    """Simulate a SQLite nmap result (finding_type is a list, no type_* booleans)."""
    return {
        "document": "",
        "metadata": {
            "tool": "nmap",
            "domain": "network",
            "severity": "informational",
            "confidence": "confirmed",
            "finding_type": ["informational"],
        },
        "distance": distance,
    }


class TestNmapDisplay:
    def test_finding_type_list_shows_in_type_column(self) -> None:
        result = _sqlite_nmap_result()
        table = _build_generic_table([result], is_semantic=False)
        rendered = _render(table)
        assert "informational" in rendered

    def test_confidence_confirmed_shows_in_table(self) -> None:
        result = _sqlite_nmap_result()
        table = _build_generic_table([result], is_semantic=False)
        rendered = _render(table)
        assert "confirmed" in rendered


# ---------------------------------------------------------------------------
# _build_osv_table — aliases and location
# ---------------------------------------------------------------------------


def _osv_result(
    aliases: Any = None,
    vulnerability_id: str = "GHSA-1234",
    source_file: str = "",
    file_path: str = "",
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "tool": "osv-scanner",
        "vulnerability_id": vulnerability_id,
        "severity": "high",
        "source_type": "lockfile",
    }
    if aliases is not None:
        meta["aliases"] = aliases
    if source_file:
        meta["source_file"] = source_file
    if file_path:
        meta["file_path"] = file_path
    return {"document": "", "metadata": meta, "distance": None}


class TestOsvTableDisplay:
    def test_aliases_as_list_renders_without_error(self) -> None:
        result = _osv_result(aliases=["CVE-2021-1234", "CVE-2021-5678"])
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "CVE-2021-1234" in rendered
        assert "CVE-2021-5678" in rendered

    def test_aliases_as_none_does_not_throw(self) -> None:
        result = _osv_result(aliases=None)
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "GHSA-1234" in rendered

    def test_location_uses_file_path_when_present(self) -> None:
        result = _osv_result(file_path="requirements.txt")
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "requirements.txt" in rendered

    def test_location_falls_back_to_source_file(self) -> None:
        result = _osv_result(source_file="go.sum")
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "go.sum" in rendered


# ---------------------------------------------------------------------------
# _build_zap_table — cwe as list
# ---------------------------------------------------------------------------


def _zap_result(
    cwe: Any = None,
    severity: str = "high",
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "tool": "zap",
        "severity": severity,
        "risk_type": "xss_reflected",
        "method": "GET",
        "url": "https://example.com/search",
        "confidence": "probable",
    }
    if cwe is not None:
        meta["cwe"] = cwe
    return {"document": "", "metadata": meta, "distance": None}


class TestZapTableDisplay:
    def test_cwe_list_renders_value(self) -> None:
        result = _zap_result(cwe=["CWE-79"])
        table = _build_zap_table([result], is_semantic=False)
        rendered = _render(table)
        assert "CWE-79" in rendered

    def test_cwe_none_renders_empty(self) -> None:
        result = _zap_result(cwe=None)
        table = _build_zap_table([result], is_semantic=False)
        rendered = _render(table)
        # CWE column header still present but no CWE value
        assert "CWE" in rendered
        assert "CWE-" not in rendered
