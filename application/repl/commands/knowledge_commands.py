"""Knowledge base commands: search, chat, stats."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from application.chat.stream_composer import RagUnavailable
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from factories.persistence import (
    ProjectNotFound,
    create_findings_service,
)

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from application.rag.knowledge_base import FindingKnowledgeBase
    from application.rag.query import QueryEngine
    from application.repl.interface import REPL

from application.repl.commands.findings_table import FindingsTableFactory


class KnowledgeCommands:
    """Handlers for knowledge base search, chat, and stats commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl
        self._findings_table_factory = FindingsTableFactory(
            tool_registry=repl.tool_registry,
        )

    # Commands

    def cmd_search(self, _cmd: str, args: list[str]) -> None:
        """Search over ingested findings. Usage: search [--flags...]"""
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
        from core.exceptions import SearchValidationError

        finding_repo = self._get_finding_repo()
        if finding_repo is None:
            return

        known_tools: frozenset[str] = frozenset(
            self.repl.tool_registry.list_tool_names()
        )

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
            table = self._findings_table_factory.build_fields(results, fields)
        else:
            table = self._findings_table_factory.build(
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
        """RAG-augmented chat with the LLM. Usage: chat <message>"""
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
        try:
            query_engine = self._get_query_engine()
        except RagUnavailable as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
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
        """Show knowledge base statistics for the active project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        try:
            kb = self._get_knowledge_base()
        except RagUnavailable as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
            return

        stats = kb.compute_stats()
        total = stats.total_documents

        if total == 0:
            self.repl.console.print("[yellow]No data ingested yet.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Total Documents", str(total))

        for tool, count in sorted(stats.by_tool.items()):
            table.add_row(f"  {tool}", str(count))

        if stats.by_severity:
            table.add_section()
            for severity, count in sorted(stats.by_severity.items()):
                table.add_row(f"  Severity: {severity}", str(count))

        if stats.last_updated:
            table.add_section()
            table.add_row("Last Updated", stats.last_updated[:19].replace("T", " "))

        self.repl.console.print(table)

    # Private helpers

    def _get_knowledge_base(self) -> FindingKnowledgeBase:
        """Return the per-project FindingKnowledgeBase.

        Raises RagUnavailable if ChromaDB or the embedding/LLM provider
        cannot be reached. The shared cache stores both successful
        builds and prior failures.
        """
        assert self.repl.active_project is not None
        knowledge_base = get_or_build_knowledge_base(
            self.repl.knowledge_base_cache,
            self.repl.active_project,
            self.repl.base_path,
        )
        if knowledge_base is None:
            raise RagUnavailable(
                "RAG engine unavailable for this project; "
                "ChromaDB or embedding provider is not reachable"
            )
        return knowledge_base

    def _get_query_engine(self) -> QueryEngine:
        """Return a QueryEngine for the active project.

        Raises RagUnavailable when the underlying knowledge base cannot
        be built.
        """
        from application.rag.query import QueryEngine

        return QueryEngine(self._get_knowledge_base())

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

        result = self._findings_table_factory.discover_tool_fields(
            finding_repo, tool_name
        )
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

    def _get_finding_repo(self) -> FindingRepositoryPort | None:
        """Return a FindingRepositoryPort for the active project, or None."""
        assert self.repl.active_project is not None
        try:
            service = create_findings_service(
                self.repl.project_registry, self._resolve_project_id()
            )
            return service.finding_repo
        except (ProjectNotFound, ValueError) as exc:
            self.repl.console.print(f"[red]Project error:[/red] {exc}")
            return None

    def _resolve_project_id(self) -> int:
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            raise ValueError(f"project not found: {self.repl.active_project}")
        return row.id
