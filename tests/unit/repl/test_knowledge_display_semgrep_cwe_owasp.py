"""Unit tests for _build_semgrep_table CWE/OWASP column."""

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
