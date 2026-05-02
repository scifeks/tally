"""Unit tests for _build_generic_table with mixed tools."""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console

from application.repl.commands.findings_table import _build_generic_table


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


def _semgrep_result(distance: float | None = None) -> dict[str, Any]:
    return {
        "document": "[semgrep] SQL injection in /src/db.py:10",
        "metadata": {
            "tool": "semgrep",
            "domain": "code",
            "severity": "high",
            "risk_type": "injection",
            "type_vulnerability": True,
        },
        "distance": distance,
    }


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


class TestGenericTable:
    def test_no_finding_column(self) -> None:
        results = [_gitleaks_result(), _semgrep_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "Finding" not in rendered

    def test_no_file_path_column(self) -> None:
        results = [_gitleaks_result(), _semgrep_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "File Path" not in rendered

    def test_no_line_column(self) -> None:
        results = [_gitleaks_result(), _semgrep_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        # "Line" also appears in "Finding"; check header row only
        # Both tools share columns, just verify Line column header absent
        assert "Line " not in rendered  # trailing space excludes "Finding"

    def test_relevance_absent_for_metadata_only(self) -> None:
        results = [_gitleaks_result(distance=None), _semgrep_result(distance=None)]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "Relevance" not in rendered

    def test_relevance_present_for_semantic(self) -> None:
        results = [_gitleaks_result(distance=0.2), _semgrep_result(distance=0.5)]
        table = _build_generic_table(results, is_semantic=True)
        rendered = _render(table)
        assert "Relevance" in rendered

    def test_both_tools_appear_in_rendered_output(self) -> None:
        results = [_gitleaks_result(), _semgrep_result()]
        table = _build_generic_table(results, is_semantic=False)
        rendered = _render(table)
        assert "gitleaks" in rendered
        assert "semgrep" in rendered
