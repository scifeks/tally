"""Gitleaks table renderer."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from application.repl.commands.findings_table import color_severity, render_finding_type


def _build_gitleaks_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build a gitleaks-specific Rich table with file path and line number columns."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("File Path", style="white", overflow="fold")
    table.add_column("Line", style="cyan", justify="right", no_wrap=True)
    table.add_column("Tool", style="cyan", no_wrap=True)
    table.add_column("Domain", style="white", no_wrap=True)
    table.add_column("Type", style="green")
    table.add_column("Severity", no_wrap=True)
    table.add_column("Confidence", no_wrap=True)
    table.add_column("Risk Type", style="dim white")
    if is_semantic:
        table.add_column("Relevance", style="dim", no_wrap=True)

    for r in results:
        meta = r["metadata"]
        sev = meta.get("severity", "")
        line_val = meta.get("line_number")
        line_str = str(int(line_val)) if line_val is not None else ""
        row: list[str] = [
            meta.get("file_path", ""),
            line_str,
            meta.get("tool", ""),
            meta.get("domain", ""),
            render_finding_type(meta),
            color_severity(sev),
            meta.get("confidence", ""),
            meta.get("risk_type", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


class GitleaksRenderer:
    tool_name = "gitleaks"
    normalized_fields: list[str] = [
        "confidence",
        "domain",
        "file_path",
        "finding_type",
        "severity",
        "tool",
    ]

    def build(self, results: list[dict[str, Any]], is_semantic: bool) -> Table:
        return _build_gitleaks_table(results, is_semantic)


renderer = GitleaksRenderer()
