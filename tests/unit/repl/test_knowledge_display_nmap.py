"""Unit tests for nmap display via _build_generic_table."""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console

from application.repl.commands.findings_table import _build_generic_table


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


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


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
