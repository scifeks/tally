"""Unit tests for _build_zap_table display."""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console

from application.repl.commands.renderers.zap import _build_zap_table


def _zap_result(
    cwe: Any = None,
    severity: str = "high",
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "tool": "zap",
        "severity": severity,
        "risk_type": "xss_reflected",
        "method": "GET",
        "url": "https://example.com/search",
        "confidence": "probable",
    }
    if cwe is not None:
        meta["cwe"] = cwe
    return {"document": "", "metadata": meta, "distance": None}


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


class TestZapTableDisplay:
    def test_cwe_list_renders_value(self) -> None:
        result = _zap_result(cwe=["CWE-79"])
        table = _build_zap_table([result], is_semantic=False)
        rendered = _render(table)
        assert "CWE-79" in rendered

    def test_cwe_none_renders_empty(self) -> None:
        result = _zap_result(cwe=None)
        table = _build_zap_table([result], is_semantic=False)
        rendered = _render(table)
        # CWE column header still present but no CWE value
        assert "CWE" in rendered
        assert "CWE-" not in rendered
