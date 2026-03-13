"""
Knowledge base commands: search, chat, stats.
todo: Refactor, this is a mess
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from core.rag.engine import RAGEngine
    from core.rag.query import QueryEngine
    from core.repl.interface import REPL

from core.tools.constants import BOOLEAN_TYPE_FIELDS


def _extract_types(meta: dict) -> str:
    """Return comma-separated list of active type_* fields."""
    active = [
        field[5:]  # strip "type_" prefix
        for field in sorted(BOOLEAN_TYPE_FIELDS)
        if meta.get(field)
    ]
    return ", ".join(active)


def _render_finding_type(meta: dict) -> str:
    """Render finding_type for display: join list, fall back to type_* booleans."""
    ft = meta.get("finding_type")
    if isinstance(ft, list):
        return ", ".join(ft)
    if isinstance(ft, str) and ft:
        return ft
    return _extract_types(meta)


_SEVERITY_COLORS = {
    "critical": "red",
    "high": "orange1",
    "medium": "yellow",
    "low": "blue",
    "informational": "white",
}


def _color_severity(sev: str) -> str:
    color = _SEVERITY_COLORS.get(sev, "white")
    return f"[{color}]{sev}[/{color}]" if sev else ""


def _all_from_tool(results: list[dict[str, Any]], tool_name: str) -> bool:
    """Return True if every result in results belongs to tool_name."""
    return bool(results) and all(
        r.get("metadata", {}).get("tool") == tool_name for r in results
    )


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
            _render_finding_type(meta),
            _color_severity(sev),
            meta.get("confidence", ""),
            meta.get("risk_type", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


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
            _color_severity(sev),
            meta.get("confidence", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


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


def _build_fields_table(results: list[dict[str, Any]], fields: list[str]) -> Table:
    """Build a custom projection table using user-specified field names."""
    table = Table(show_header=True, header_style="bold")
    for f in fields:
        table.add_column(f, overflow="fold")
    for r in results:
        meta = r["metadata"]
        row: list[str] = []
        for f in fields:
            val = meta.get(f)
            if val is None:
                row.append("N/A")
            elif f == "severity":
                row.append(_color_severity(str(val)))
            elif isinstance(val, list):
                row.append(", ".join(str(v) for v in val))
            else:
                row.append(str(val))
        table.add_row(*row)
    return table


def _build_generic_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build the generic findings Rich table."""
    table = Table(show_header=True, header_style="bold")
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
        row: list[str] = [
            meta.get("tool", ""),
            meta.get("domain", ""),
            _render_finding_type(meta),
            _color_severity(sev),
            meta.get("confidence", ""),
            meta.get("risk_type", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


# Per-tool normalized field names (ChromaDB names, not SQLite column names).
# Used by --show-fields to cross-reference schema columns relevant to each tool.
_TOOL_NORMALIZED_FIELDS: dict[str, list[str]] = {
    "gitleaks": [
        "confidence",
        "domain",
        "file_path",
        "finding_type",
        "severity",
        "tool",
    ],
    "semgrep": ["confidence", "cwe", "file_path", "finding_type", "rule_id"],
    "zap": ["confidence", "cwe", "severity", "url"],
    "osv-scanner": [
        "ecosystem",
        "file_path",
        "finding_type",
        "package_name",
        "severity",
        "vulnerability_id",
    ],
    "nmap": [
        "confidence",
        "domain",
        "finding_type",
        "ip_address",
        "port",
        "severity",
    ],
}

# Fallback: all normalized fields for tools not in the mapping above
_ALL_NORMALIZED_FIELDS: list[str] = [
    "confidence",
    "cwe",
    "description",
    "domain",
    "ecosystem",
    "file_path",
    "finding_type",
    "ip_address",
    "package_name",
    "package_version",
    "port",
    "rule_id",
    "severity",
    "tool",
    "url",
    "vulnerability_id",
]


def _discover_tool_fields(sqlite_store: Any, tool_name: str) -> list[str] | None:
    """Return sorted field list for tool_name, or None if no rows exist."""
    count, meta_keys = sqlite_store.get_tool_meta_keys(tool_name)
    if count == 0:
        return None
    normalized = set(_TOOL_NORMALIZED_FIELDS.get(tool_name, _ALL_NORMALIZED_FIELDS))
    return sorted(normalized | meta_keys)


class KnowledgeCommands:
    """Handlers for knowledge base search, chat, and stats commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_search(self, _cmd: str, args: list[str]) -> None:
        """search [--flags...]  — search over ingested findings."""
        # --help is allowed without an active project
        if "--help" in args:
            from core.repl.interface import _build_search_help_table

            self.repl.console.print(_build_search_help_table())
            return

        # --show-fields is a boolean flag; intercept before the main parser
        if "--show-fields" in args or any(a.startswith("--show-fields=") for a in args):
            self._cmd_show_fields(args)
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch' first.[/yellow]"
            )
            return

        from core.store.sqlite_store import (
            SearchValidationError,
            parse_sqlite_search_command,
        )
        from core.tools.registry import tool_registry

        sqlite_store = self._get_sqlite_store()
        if sqlite_store is None:
            return

        known_tools: frozenset[str] = frozenset(tool_registry.list_tool_names())

        try:
            filters = parse_sqlite_search_command(args, known_tools)
        except SearchValidationError as exc:
            self.repl.console.print(f"[red]Search error:[/red] {exc}")
            return

        try:
            with self.repl.console.status("Searching knowledge base..."):
                results = sqlite_store.search(filters)
        except Exception as exc:
            self.repl.console.print(f"[red]Search error:[/red] {exc}")
            return

        if not results:
            self.repl.console.print("[yellow]No findings matched your search.[/yellow]")
            return

        is_semantic = False  # SQLite results are never semantic

        fields = filters.get("fields", [])
        if fields:
            table = _build_fields_table(results, fields)
        elif _all_from_tool(results, "gitleaks"):
            table = _build_gitleaks_table(results, is_semantic)
        elif _all_from_tool(results, "semgrep"):
            table = _build_semgrep_table(results, is_semantic)
        elif _all_from_tool(results, "zap"):
            table = _build_zap_table(results, is_semantic)
        elif _all_from_tool(results, "osv-scanner"):
            table = _build_osv_table(results, is_semantic)
        else:
            table = _build_generic_table(results, is_semantic)

        self.repl.console.print(table)

        # Pagination hint
        shown = len(results)
        page = filters.get("page", 1)
        page_size = filters.get("page_size", 200)
        if page > 1 or shown == page_size:
            page_hint = f"Page {page} · {shown} results"
            if shown == page_size:
                page_hint += f"  [dim]Use --page={page + 1} for next page[/dim]"
            self.repl.console.print(f"[dim]{page_hint}[/dim]")

    def cmd_chat(self, _cmd: str, args: list[str]) -> None:
        """chat <message>  — RAG-augmented chat with the LLM."""
        if not args:
            self.repl.console.print("[red]Usage:[/red] chat <message>")
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        message = " ".join(args)
        query_engine = self._get_query_engine()
        if query_engine is None:
            return

        with self.repl.console.status("Thinking..."):
            response = query_engine.chat(message)

        self.repl.console.print(
            Panel(
                response,
                title="[bold]Assistant[/bold]",
                border_style="cyan",
                expand=False,
            )
        )

    def cmd_stats(self, _cmd: str, _args: list[str]) -> None:
        """stats  — show knowledge base statistics for the active project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        rag_engine = self._get_rag_engine()
        if rag_engine is None:
            return

        stats = rag_engine.get_stats()
        total = stats.get("total_documents", 0)

        if total == 0:
            self.repl.console.print("[yellow]No data ingested yet.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Total Documents", str(total))

        for tool, count in sorted(stats.get("by_tool", {}).items()):
            table.add_row(f"  {tool}", str(count))

        for severity, count in sorted(stats.get("by_severity", {}).items()):
            table.add_row(f"  Severity: {severity}", str(count))

        last_updated = stats.get("last_updated")
        if last_updated:
            table.add_row("Last Updated", last_updated[:19].replace("T", " "))

        self.repl.console.print(table)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_rag_engine(self) -> RAGEngine | None:
        """Create and return a RAGEngine for the active project, or None on error."""
        from core.rag import RAGEngine

        assert self.repl.active_project is not None
        try:
            return RAGEngine(
                project_name=self.repl.active_project,
                base_path=self.repl.base_path,
            )
        except RuntimeError as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
            return None
        except ValueError as exc:
            self.repl.console.print(f"[red]Project error:[/red] {exc}")
            return None

    def _get_query_engine(self) -> QueryEngine | None:
        """Create and return a QueryEngine for the active project, or None on error."""
        from core.rag.query import QueryEngine

        rag_engine = self._get_rag_engine()
        if rag_engine is None:
            return None
        return QueryEngine(rag_engine)

    def _cmd_show_fields(self, args: list[str]) -> None:
        """Handle search --show-fields --tool=<name>."""
        # Reject --show-fields=<value> (flag takes no value)
        if any(a.startswith("--show-fields=") for a in args):
            self.repl.console.print(
                "[red]Error:[/red] --show-fields takes no value.\n"
                "Usage: search --show-fields --tool=<tool_name>"
            )
            return

        rest = [a for a in args if a != "--show-fields"]

        # Must be exactly: --tool=<single_tool_name>, nothing else
        if len(rest) != 1 or not rest[0].startswith("--tool="):
            self.repl.console.print(
                "[red]Error:[/red] --show-fields requires exactly "
                "--tool=<tool_name> and no other flags.\n"
                "Usage: search --show-fields --tool=<tool_name>"
            )
            return

        tool_name = rest[0][len("--tool=") :]
        if not tool_name or "," in tool_name:
            self.repl.console.print(
                "[red]Error:[/red] --show-fields requires a single tool name "
                "(not a comma-separated list).\n"
                "Usage: search --show-fields --tool=<tool_name>"
            )
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch' first.[/yellow]"
            )
            return

        sqlite_store = self._get_sqlite_store()
        if sqlite_store is None:
            return

        fields = _discover_tool_fields(sqlite_store, tool_name)
        if fields is None:
            self.repl.console.print(
                f"[yellow]No findings found for tool '{tool_name}'. "
                "Cannot show fields.[/yellow]"
            )
            return

        self.repl.console.print(", ".join(fields))

    def _get_sqlite_store(self):  # type: ignore[return]
        """Return a SQLiteStore for the active project, or None on error."""
        from core.store.sqlite_store import SQLiteStore

        assert self.repl.active_project is not None
        try:
            store = SQLiteStore(self.repl.base_path, self.repl.active_project)
            store._init_schema()
            return store
        except Exception as exc:
            self.repl.console.print(f"[red]SQLite error:[/red] {exc}")
            return None
