"""Knowledge base commands: search, chat, stats."""

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
            _extract_types(meta),
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
            _extract_types(meta),
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
        cwe_id = meta.get("cwe_id")
        cwe_str = f"CWE-{cwe_id}" if cwe_id is not None else ""
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
        aliases = meta.get("aliases", "")
        vuln_id = meta.get("vulnerability_id", "")
        ids = ", ".join(filter(None, [vuln_id, aliases])) if aliases else vuln_id
        row: list[str] = [
            meta.get("source_type", ""),
            meta.get("lockfile", meta.get("source_file", "")),
            _extract_types(meta),
            _color_severity(sev),
            "probable",
            ids,
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


def _build_generic_table(results: list[dict[str, Any]], is_semantic: bool) -> Table:
    """Build the generic findings Rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Finding", style="white", max_width=50)
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
        doc_text = r["document"][:80].replace("\n", " ") if r["document"] else ""
        sev = meta.get("severity", "")
        row: list[str] = [
            doc_text,
            meta.get("tool", ""),
            meta.get("domain", ""),
            _extract_types(meta),
            _color_severity(sev),
            meta.get("confidence", ""),
            meta.get("risk_type", ""),
        ]
        if is_semantic:
            dist = r["distance"]
            row.append(f"{dist:.3f}" if dist is not None else "")
        table.add_row(*row)

    return table


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

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch' first.[/yellow]"
            )
            return

        from core.rag.search_parser import SearchValidationError, parse_search_command

        query_engine = self._get_query_engine()
        if query_engine is None:
            return

        try:
            query = parse_search_command(args, query_engine._known_tools)
        except SearchValidationError as exc:
            self.repl.console.print(f"[red]Search error:[/red] {exc}")
            return

        try:
            with self.repl.console.status("Searching knowledge base..."):
                results = query_engine.search(query=query)
        except SearchValidationError as exc:
            self.repl.console.print(f"[red]Search error:[/red] {exc}")
            return

        if not results:
            self.repl.console.print("[yellow]No findings matched your search.[/yellow]")
            return

        is_semantic = results[0]["distance"] is not None

        if _all_from_tool(results, "gitleaks"):
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

        # Pagination hint — use pre-parsed query directly, no re-parse needed
        shown = len(results)
        if query.page > 1 or shown == query.page_size:
            page_hint = f"Page {query.page} · {shown} results"
            if shown == query.page_size:
                page_hint += f"  [dim]Use --page={query.page + 1} for next page[/dim]"
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
