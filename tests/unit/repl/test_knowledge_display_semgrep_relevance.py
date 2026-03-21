"""Unit tests for _build_semgrep_table relevance column."""

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
