"""Unit tests for _build_semgrep_table location formatting."""

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
