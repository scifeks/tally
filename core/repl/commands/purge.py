"""Purge command: delete findings from the knowledge base."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape

if TYPE_CHECKING:
    from core.rag.engine import RAGEngine
    from core.repl.interface import REPL

# Help text exposed as a class attribute so smoke tests can find it.
_HELP_TEXT = (
    "purge [--tool <tool>]\n"
    "\n"
    "  --tool <tool>   Delete all findings from the specified tool\n"
    "\n"
    "  With no arguments, deletes ALL findings and clears all tool output files.\n"
    "\n"
    "  Examples:\n"
    "    purge\n"
    "    purge --tool nmap\n"
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
        """purge [--tool <tool>]  — delete findings."""
        tool, args = self._parse_value_flag(args, "--tool")

        # Reject bare positional arguments (e.g. `purge gitleaks`)
        if args:
            extra = " ".join(args)
            msg = f"[red]Error:[/red] Unexpected argument(s): {extra}"
            if len(args) == 1:
                msg += f"\nDid you mean: [bold]purge --tool {args[0]}[/bold]?"
            self.repl.console.print(msg)
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
        count = self._count_matching(rag_engine, tool=tool)

        if count == 0:
            self.repl.console.print("[yellow]No matching documents found.[/yellow]")
            return

        # Build confirmation prompt
        if tool is not None:
            confirm_msg = f"Delete all {tool} findings?"
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

        deleted = rag_engine.delete_findings(tool=tool)
        self._delete_tool_output_files(tool=tool)
        self.repl.console.print(f"[green]Deleted {deleted} document(s).[/green]")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _delete_tool_output_files(self, tool: str | None) -> None:
        """Delete files from tool_outputs directories.

        If tool is given, delete all files in tool_outputs/<tool>/ (keep dir).
        If tool is None, delete files in all tool_outputs subdirs (keep dirs).
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

        if tool is not None:
            dirs_to_clear = [tool_outputs_dir / tool]
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
        tool: str | None,
    ) -> int:
        """Return the count of documents that match the given filters."""
        if rag_engine._collection is None:
            return 0

        if tool is not None:
            where: dict[str, str] = {"tool": tool}
            try:
                result = rag_engine._collection.get(where=where, include=[])  # type: ignore[arg-type]
                return len(result.get("ids") or [])
            except Exception:
                return 0

        return rag_engine.count_documents()

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
