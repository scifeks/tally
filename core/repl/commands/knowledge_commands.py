"""Knowledge base commands: search, chat, stats."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from core.rag.engine import RAGEngine
    from core.rag.query import QueryEngine
    from core.repl.interface import REPL

# Keys that have their own dedicated column — excluded from the Info column.
_SEARCH_DEDICATED_KEYS = frozenset(
    {
        "tool",
        "finding_type",
        "ip_address",
        "port",
        "service",
        "hostname",
        "transport",
        "cve_ids",
    }
)


class KnowledgeCommands:
    """Handlers for knowledge base search, chat, and stats commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_search(self, _cmd: str, args: list[str]) -> None:
        """search <query>  — semantic search over ingested findings."""
        if not args:
            self.repl.console.print("[red]Usage:[/red] search <query>")
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        query = " ".join(args)
        query_engine = self._get_query_engine()
        if query_engine is None:
            return

        with self.repl.console.status("Searching knowledge base..."):
            results = query_engine.search(query)

        if not results:
            self.repl.console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Tool", style="cyan", no_wrap=True)
        table.add_column("Type", style="green", no_wrap=True)
        table.add_column("IP", style="white", no_wrap=True)
        table.add_column("Hostname", style="white", no_wrap=True)
        table.add_column("Port", style="white", no_wrap=True)
        table.add_column("Transport", style="white", no_wrap=True)
        table.add_column("Service", style="white", no_wrap=True)
        table.add_column("CVE IDs", style="red", max_width=30)
        table.add_column("Info", style="dim white", max_width=50)

        for r in results:
            meta = r["metadata"]

            port_val = meta["port"] if "port" in meta else ""
            info = "  ".join(
                f"{k}={v}" for k, v in meta.items() if k not in _SEARCH_DEDICATED_KEYS
            )

            table.add_row(
                meta.get("tool", ""),
                meta.get("finding_type", ""),
                meta.get("ip_address", ""),
                meta.get("hostname", ""),
                str(port_val),
                meta.get("transport", ""),
                meta.get("service", ""),
                meta.get("cve_ids", ""),
                info,
            )

        self.repl.console.print(table)

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
