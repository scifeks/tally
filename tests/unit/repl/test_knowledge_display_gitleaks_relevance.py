"""Unit tests for _build_gitleaks_table relevance column."""

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
