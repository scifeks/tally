"""OSV-Scanner table renderer."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from core.repl.commands.findings_table import _color_severity, _render_finding_type


def _build_osv_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build an osv-scanner-specific Rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Source Type", style="dim white", no_wrap=True)
    table.add_column("Location", style="white", overflow="fold")
    table.add_column("Type", style="green")
    table.add_column("Severity", no_wrap=True)
    table.add_column("Confidence", no_wrap=True)
    table.add_column("IDs", style="cyan", overflow="fold")
    if is_semantic:
        table.add_column("Relevance", style="dim", no_wrap=True)

    for r in results:
        meta = r["metadata"]
        sev = meta.get("severity", "")
        aliases_raw = meta.get("aliases")
        aliases_str = (
            ", ".join(aliases_raw)
            if isinstance(aliases_raw, list)
            else (aliases_raw or "")
        )
        vuln_id = meta.get("vulnerability_id", "")
        ids = (
            ", ".join(filter(None, [vuln_id, aliases_str])) if aliases_str else vuln_id
        )
        row: list[str] = [
            meta.get("source_type", ""),
            meta.get("file_path") or meta.get("source_file", ""),
            _render_finding_type(meta),
            _color_severity(sev),
            "probable",
            ids,
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


class OsvScannerRenderer:
    tool_name = "osv-scanner"
    normalized_fields: list[str] = [
        "ecosystem",
        "file_path",
        "finding_type",
        "package_name",
        "severity",
        "vulnerability_id",
    ]

    def build(self, results: list[dict[str, Any]], is_semantic: bool) -> Table:
        return _build_osv_table(results, is_semantic)


renderer = OsvScannerRenderer()
