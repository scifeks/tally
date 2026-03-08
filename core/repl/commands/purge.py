"""Purge command: delete findings from the knowledge base."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.rag.engine import RAGEngine
    from core.repl.interface import REPL

# Help text exposed as a class attribute so smoke tests can find it.
_HELP_TEXT = (
    "purge [--tool <tool>] [--profile <profile>]\n"
    "\n"
    "  --tool <tool>               Delete all findings from the specified tool\n"
    "  --tool <tool> --profile <p> Delete findings for a specific tool+profile\n"
    "\n"
    "  Examples:\n"
    "    purge --tool nmap\n"
    "    purge --tool nmap --profile management\n"
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
        """purge [--tool <tool>] [--profile <profile>]  — delete findings."""
        tool, args = self._parse_value_flag(args, "--tool")
        profile, args = self._parse_value_flag(args, "--profile")

        if profile is not None and tool is None:
            self.repl.console.print(
                "[red]Error:[/red] --profile requires --tool to be specified"
            )
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        rag_engine = self._get_rag_engine()
        if rag_engine is None:
            return

        # Count matching documents before deletion
        count = self._count_matching(rag_engine, tool=tool, profile=profile)

        if count == 0:
            self.repl.console.print("[yellow]No matching documents found.[/yellow]")
            return

        # Build confirmation prompt
        if tool is not None and profile is not None:
            label = f"{tool}/{profile}"
            confirm_msg = f"Delete {label} findings?"
        elif tool is not None:
            label = tool
            confirm_msg = f"Delete all {label} findings?"
        else:
            label = "all"
            confirm_msg = "Delete ALL findings?"

        self.repl.console.print(
            f"Found [bold]{count}[/bold] document(s). {confirm_msg} [y/N] ",
            end="",
        )
        answer = input().strip().lower()
        if answer != "y":
            self.repl.console.print("[dim]Aborted.[/dim]")
            return

        deleted = rag_engine.delete_findings(tool=tool, profile=profile)
        self.repl.console.print(f"[green]Deleted {deleted} document(s).[/green]")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _count_matching(
        self,
        rag_engine: RAGEngine,
        tool: str | None,
        profile: str | None,
    ) -> int:
        """Return the count of documents that match the given filters."""
        if rag_engine._collection is None:
            return 0

        if tool is not None and profile is not None:
            where = {"$and": [{"tool": tool}, {"profile": profile}]}
        elif tool is not None:
            where = {"tool": tool}
        else:
            # No filters — count everything
            return rag_engine.count_documents()

        try:
            result = rag_engine._collection.get(where=where, include=[])
            return len(result.get("ids") or [])
        except Exception:
            return 0

    def _get_rag_engine(self) -> RAGEngine | None:
        """Create and return a RAGEngine for the active project, or None on error."""
        from core.rag import RAGEngine

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

    @staticmethod
    def _parse_value_flag(args: list[str], *flags: str) -> tuple[str | None, list[str]]:
        """Extract a value flag (e.g. --tool nmap).

        Returns (value_or_None, remaining_args).
        """
        for i, token in enumerate(args):
            if token in flags and i + 1 < len(args):
                value = args[i + 1]
                remaining = args[:i] + args[i + 2 :]
                return value, remaining
        return None, args
