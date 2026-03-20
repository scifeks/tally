"""ZAP table renderer."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from application.repl.commands.findings_table import color_severity


def _build_zap_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build a ZAP-specific Rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Alert", style="white", overflow="fold")
    table.add_column("Method", style="cyan", no_wrap=True)
    table.add_column("URL", style="white", overflow="fold")
    table.add_column("CWE", style="dim white", no_wrap=True)
    table.add_column("Severity", no_wrap=True)
    table.add_column("Confidence", no_wrap=True)
    if is_semantic:
        table.add_column("Relevance", style="dim", no_wrap=True)

    for r in results:
        meta = r["metadata"]
        sev = meta.get("severity", "")
        cwe_list = meta.get("cwe") or []
        cwe_str = (
            ", ".join(cwe_list) if isinstance(cwe_list, list) else str(cwe_list or "")
        )
        row: list[str] = [
            meta.get("risk_type", ""),
            meta.get("method", ""),
            meta.get("url", ""),
            cwe_str,
            color_severity(sev),
            meta.get("confidence", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


class ZapRenderer:
    tool_name = "zap"
    normalized_fields: list[str] = ["confidence", "cwe", "severity", "url"]

    def build(self, results: list[dict[str, Any]], is_semantic: bool) -> Table:
        return _build_zap_table(results, is_semantic)


renderer = ZapRenderer()
