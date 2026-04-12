"""Knowledge base commands: search, chat, stats."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from application.rag.engine import RAGEngine
    from application.rag.query import QueryEngine
    from application.repl.interface import REPL

from application.repl.commands.findings_table import FindingsTableFactory

_findings_table_factory = FindingsTableFactory()


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
            from application.repl.interface import _build_search_help_table

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

        from application.repl.search_command_parser import parse_sqlite_search_command
        from application.tools.registry import tool_registry
        from core.exceptions import SearchValidationError

        finding_repo = self._get_finding_repo()
        if finding_repo is None:
            return

        known_tools: frozenset[str] = frozenset(tool_registry.list_tool_names())

        try:
            filters = parse_sqlite_search_command(args, known_tools)
        except SearchValidationError as exc:
            self.repl.console.print(f"[red]Search error:[/red] {exc}")
            return

        try:
            with self.repl.console.status("Searching knowledge base..."):
                results = finding_repo.search(filters)
        except Exception as exc:
            self.repl.console.print(f"[red]Search error:[/red] {exc}")
            return

        if not results:
            self.repl.console.print("[yellow]No findings matched your search.[/yellow]")
            return

        is_semantic = False  # SQLite results are never semantic

        fields = filters.get("fields", [])
        tool_filter: str | None = filters.get("tool") if not fields else None
        if fields:
            table = _findings_table_factory.build_fields(results, fields)
        else:
            table = _findings_table_factory.build(
                results, is_semantic, tool_filter=tool_filter
            )

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

        try:
            with self.repl.console.status("Thinking..."):
                response = query_engine.chat(message)
        except Exception as exc:
            self.repl.console.print(f"[red]Chat error:[/red] {exc}")
            return

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

        by_severity = stats.get("by_severity", {})
        if by_severity:
            table.add_section()
            for severity, count in sorted(by_severity.items()):
                table.add_row(f"  Severity: {severity}", str(count))

        last_updated = stats.get("last_updated")
        if last_updated:
            table.add_section()
            table.add_row("Last Updated", last_updated[:19].replace("T", " "))

        self.repl.console.print(table)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_rag_engine(self) -> RAGEngine | None:
        """Create and return a RAGEngine for the active project, or None on error."""
        from application.rag import RAGEngine

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
        from application.rag.query import QueryEngine

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

        finding_repo = self._get_finding_repo()
        if finding_repo is None:
            return

        result = _findings_table_factory.discover_tool_fields(finding_repo, tool_name)
        if result is None:
            self.repl.console.print(
                f"[yellow]No findings found for tool '{tool_name}'. "
                "Cannot show fields.[/yellow]"
            )
            return

        schema_fields, meta_fields = result
        self.repl.console.print(f"Schema fields: {', '.join(schema_fields)}")
        if meta_fields:
            self.repl.console.print(f"Meta fields:   {', '.join(meta_fields)}")

    def _get_finding_repo(self):  # type: ignore[return]
        """Return a FindingRepository for the active project, or None on error."""
        from infrastructure.store import make_store

        assert self.repl.active_project is not None
        try:
            _, finding_repo, _, _ = make_store(
                self.repl.base_path, self.repl.active_project
            )
            return finding_repo
        except Exception as exc:
            self.repl.console.print(f"[red]SQLite error:[/red] {exc}")
            return None
