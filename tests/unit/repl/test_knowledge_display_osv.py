"""Unit tests for _build_osv_table display."""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console

from application.repl.commands.renderers.osv_scanner import _build_osv_table


def _osv_result(
    aliases: Any = None,
    vulnerability_id: str = "GHSA-1234",
    source_file: str = "",
    file_path: str = "",
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "tool": "osv-scanner",
        "vulnerability_id": vulnerability_id,
        "severity": "high",
        "source_type": "lockfile",
    }
    if aliases is not None:
        meta["aliases"] = aliases
    if source_file:
        meta["source_file"] = source_file
    if file_path:
        meta["file_path"] = file_path
    return {"document": "", "metadata": meta, "distance": None}


def _render(table: Any, width: int = 500) -> str:
    """Render a Rich table to a plain string (no ANSI codes)."""
    out = StringIO()
    console = Console(file=out, width=width, highlight=False, no_color=True)
    console.print(table)
    return out.getvalue()


class TestOsvTableDisplay:
    def test_aliases_as_list_renders_without_error(self) -> None:
        result = _osv_result(aliases=["CVE-2021-1234", "CVE-2021-5678"])
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "CVE-2021-1234" in rendered
        assert "CVE-2021-5678" in rendered

    def test_aliases_as_none_does_not_throw(self) -> None:
        result = _osv_result(aliases=None)
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "GHSA-1234" in rendered

    def test_location_uses_file_path_when_present(self) -> None:
        result = _osv_result(file_path="requirements.txt")
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "requirements.txt" in rendered

    def test_location_falls_back_to_source_file(self) -> None:
        result = _osv_result(source_file="go.sum")
        table = _build_osv_table([result], is_semantic=False)
        rendered = _render(table)
        assert "go.sum" in rendered
