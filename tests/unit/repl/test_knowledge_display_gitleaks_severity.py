"""Unit tests for _build_gitleaks_table severity rendering."""

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


class TestGitleaksTableSeverity:
    def test_severity_value_rendered(self) -> None:
        table = _build_gitleaks_table(
            [_gitleaks_result(severity="high")], is_semantic=False
        )
        rendered = _render(table)
        assert "high" in rendered

    def test_critical_severity_uses_red_markup(self) -> None:
        from application.repl.commands.findings_table import color_severity

        markup = color_severity("critical")
        assert "[red]" in markup
        assert "critical" in markup

    def test_informational_severity_uses_white_markup(self) -> None:
        from application.repl.commands.findings_table import color_severity

        markup = color_severity("informational")
        assert "[white]" in markup

    def test_medium_severity_uses_yellow_markup(self) -> None:
        from application.repl.commands.findings_table import color_severity

        markup = color_severity("medium")
        assert "[yellow]" in markup

    def test_low_severity_uses_blue_markup(self) -> None:
        from application.repl.commands.findings_table import color_severity

        markup = color_severity("low")
        assert "[blue]" in markup
