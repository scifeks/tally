"""Semgrep table renderer."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from core.repl.commands.findings_table import _render_finding_type


def _build_semgrep_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build a semgrep-specific Rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Rule ID", style="white", overflow="fold")
    table.add_column("Location", style="cyan", overflow="fold")
    table.add_column("Type", style="green")
    table.add_column("Confidence", no_wrap=True)
    table.add_column("CWE / OWASP", style="dim white")
    if is_semantic:
        table.add_column("Relevance", style="dim", no_wrap=True)

    for r in results:
        meta = r["metadata"]
        file_path = meta.get("file_path", "")
        line_start = meta.get("line_start")
        location = (
            f"{file_path}:{int(line_start)}" if line_start is not None else file_path
        )
        cwe_raw = meta.get("cwe", "")
        owasp_raw = meta.get("owasp", "")
        cwe = ", ".join(cwe_raw) if isinstance(cwe_raw, list) else (cwe_raw or "")
        owasp = (
            ", ".join(owasp_raw) if isinstance(owasp_raw, list) else (owasp_raw or "")
        )
        cwe_owasp = " / ".join(filter(None, [cwe, owasp]))
        row: list[str] = [
            meta.get("rule_id", ""),
            location,
            _render_finding_type(meta),
            meta.get("confidence", ""),
            cwe_owasp,
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


class SemgrepRenderer:
    tool_name = "semgrep"
    normalized_fields: list[str] = [
        "confidence",
        "cwe",
        "file_path",
        "finding_type",
        "rule_id",
    ]

    def build(self, results: list[dict[str, Any]], is_semantic: bool) -> Table:
        return _build_semgrep_table(results, is_semantic)


renderer = SemgrepRenderer()
