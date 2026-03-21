"""Unit tests for _build_gitleaks_table column headers."""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console

from application.repl.commands.renderers.gitleaks import _build_gitleaks_table


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


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


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
