"""Unit tests for _build_semgrep_table column headers."""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console

from application.repl.commands.renderers.semgrep import _build_semgrep_table


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


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


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
