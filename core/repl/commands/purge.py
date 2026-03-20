"""Purge command: delete findings from the knowledge base."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape

from application.tools.registry import tool_registry

if TYPE_CHECKING:
    from application.rag.engine import RAGEngine
    from core.repl.interface import REPL

# Help text exposed as a class attribute so smoke tests can find it.
_HELP_TEXT = (
    "purge [--tool=<tool,...>]\n"
    "\n"
    "  --tool=<tool,...>   Delete findings from the specified tool(s).\n"
    "                      Comma-separated list accepted.\n"
    "\n"
    "  With no arguments, deletes ALL findings and clears all tool output files.\n"
    "\n"
    "  Examples:\n"
    "    purge\n"
    "    purge --tool=nmap\n"
    "    purge --tool=semgrep,gitleaks\n"
)


class PurgeCommand:
    """Handler for the 'purge' REPL command."""

    help_text: str = _HELP_TEXT

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Command entry point
    # ------------------------------------------------------------------

    def cmd_purge(self, _cmd: str, args: list[str]) -> None:
        """purge [--tool=<tool,...>]  — delete findings."""
        tool_val: str | None = None
        unrecognized: list[str] = []

        for arg in args:
            if arg.startswith("--tool="):
                tool_val = arg[7:]
            elif arg == "--tool":
                self.repl.console.print(
                    "[red]Error:[/red] Use --tool=<tool> (equals sign),"
                    " not --tool <tool>\n"
                    "Example: purge --tool=semgrep"
                )
                return
            else:
                unrecognized.append(arg)

        if unrecognized:
            self.repl.console.print(
                f"[red]Unrecognized argument(s):[/red] {', '.join(unrecognized)}\n"
                "Usage: purge [--tool=<tool,...>]"
            )
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        # Validate --tool
        tools: list[str] | None = None
        if tool_val is not None:
            tools = [t.strip() for t in tool_val.split(",") if t.strip()]
            known = set(tool_registry.list_tool_names())
            invalid = [t for t in tools if t not in known]
            if invalid:
                self.repl.console.print(
                    f"[red]Unknown tool(s):[/red] {', '.join(invalid)}\n"
                    f"Configured tools: {', '.join(sorted(known))}"
                )
                return

        rag_engine = self._get_rag_engine()
        if rag_engine is None:
            return

        count = self._count_matching(rag_engine, tools=tools)
        if count == 0:
            self.repl.console.print("[yellow]No matching documents found.[/yellow]")
            return

        # Build confirmation prompt
        if tools is not None:
            tools_str = ", ".join(tools)
            confirm_msg = f"Delete all {tools_str} findings?"
        else:
            confirm_msg = "Delete ALL findings?"

        self.repl.console.print(
            f"Found [bold]{count}[/bold] document(s). {confirm_msg} {escape('[y/N]')} ",
            end="",
        )
        answer = input().strip().lower()
        if answer != "y":
            self.repl.console.print("[dim]Aborted.[/dim]")
            return

        total_deleted = 0
        if tools is not None:
            for t in tools:
                total_deleted += rag_engine.delete_findings(tool=t)
        else:
            total_deleted = rag_engine.delete_findings(tool=None)
        self._delete_tool_output_files(tools=tools)
        self._purge_sqlite(tools=tools)
        self.repl.console.print(f"[green]Deleted {total_deleted} document(s).[/green]")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _delete_tool_output_files(self, tools: list[str] | None) -> None:
        """Delete files from tool_outputs directories.

        If tools is given, delete all files in tool_outputs/<tool>/ for each tool.
        If tools is None, delete files in all tool_outputs subdirs (keep dirs).
        """
        assert self.repl.active_project is not None
        tool_outputs_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "tool_outputs"
        )
        if not tool_outputs_dir.exists():
            return

        if tools is not None:
            dirs_to_clear = [tool_outputs_dir / t for t in tools]
        else:
            dirs_to_clear = [d for d in tool_outputs_dir.iterdir() if d.is_dir()]

        for tool_dir in dirs_to_clear:
            if not tool_dir.exists():
                continue
            for item in tool_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    def _count_matching(
        self,
        rag_engine: RAGEngine,
        tools: list[str] | None,
    ) -> int:
        """Return the count of documents that match the given filters."""
        if tools is not None:
            total = 0
            for t in tools:
                where: dict[str, str] = {"tool": t}
                try:
                    result = rag_engine.get_documents(where=where, include=[])  # type: ignore[arg-type]
                    total += len(result.get("ids") or [])
                except Exception:
                    pass
            return total

        return rag_engine.count_documents()

    def _purge_sqlite(self, tools: list[str] | None) -> None:
        """Delete SQLite findings for the given tools, or full wipe if None."""
        assert self.repl.active_project is not None
        try:
            from pathlib import Path

            from infrastructure.store.connection import ConnectionFactory
            from infrastructure.store.repositories.findings import FindingRepository

            db_path = (
                Path(self.repl.base_path)
                / "projects"
                / self.repl.active_project
                / "sqlite"
                / "findings.db"
            )
            factory = ConnectionFactory(db_path)
            if tools is None:
                # Full wipe: delete and recreate the database file
                if factory.db_path.exists():
                    factory.db_path.unlink()
                factory.init_schema()
            else:
                FindingRepository(factory).delete_findings(tools=tools)
        except Exception as exc:
            self.repl.console.print(f"[yellow]SQLite purge warning:[/yellow] {exc}")

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
