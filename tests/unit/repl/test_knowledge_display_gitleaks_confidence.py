"""Unit tests for _build_gitleaks_table confidence column."""

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
