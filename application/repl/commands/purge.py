"""Purge command: delete findings from the knowledge base."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape

from application.chat.stream_composer import RagUnavailable
from application.purge.service import PurgeService
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from core.project_paths import ProjectPaths

if TYPE_CHECKING:
    from application.rag.knowledge_base import FindingKnowledgeBase
    from application.repl.interface import REPL


def _project_paths(repl: REPL) -> ProjectPaths:
    assert repl.active_project is not None
    return ProjectPaths.from_canonical(repl.base_path, repl.active_project)


# Help text exposed as a class attribute so smoke tests can find it.
_HELP_TEXT = (
    "purge [--tool=<tool,...>] [--keep-reports]\n"
    "\n"
    "  --tool=<tool,...>   Delete findings from the specified tool(s).\n"
    "                      Comma-separated list accepted.\n"
    "                      Does not affect other tools or reports.\n"
    "\n"
    "  --keep-reports      Skip deleting generated reports.\n"
    "                      Only applies on a full purge (no --tool).\n"
    "\n"
    "  With no arguments, deletes ALL findings, clears all tool output files,\n"
    "  and deletes all generated reports in the project reports/ directory.\n"
    "  A second prompt asks whether to also delete merged endpoint URL files\n"
    "  (endpoints/<repo>/merged_oas3.json and merged_urls.txt). User-provided\n"
    "  seed files under config/endpoints/ are never deleted by purge.\n"
    "\n"
    "  Examples:\n"
    "    purge\n"
    "    purge --keep-reports\n"
    "    purge --tool=gitleaks\n"
    "    purge --tool=semgrep,gitleaks\n"
)


class PurgeCommand:
    """Handler for the 'purge' REPL command."""

    help_text: str = _HELP_TEXT

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # Command entry point

    def cmd_purge(self, _cmd: str, args: list[str]) -> None:
        """purge [--tool=<tool,...>] [--keep-reports]: delete findings."""
        tool_val: str | None = None
        keep_reports: bool = False
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
            elif arg == "--keep-reports":
                keep_reports = True
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
            known = set(self.repl.tool_registry.list_tool_names())
            invalid = [t for t in tools if t not in known]
            if invalid:
                self.repl.console.print(
                    f"[red]Unknown tool(s):[/red] {', '.join(invalid)}\n"
                    f"Configured tools: {', '.join(sorted(known))}"
                )
                return

        try:
            kb = self._get_knowledge_base()
        except RagUnavailable as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
            return

        project_id = self._resolve_project_id()
        if project_id is None:
            self.repl.console.print("[red]Error:[/red] Could not resolve project ID")
            return

        project_paths = _project_paths(self.repl)
        service = PurgeService(
            kb,
            project_paths,
            self.repl.project_registry,
            project_id,
        )

        analysis = service.analyze(tools, keep_reports)

        if not analysis.has_anything:
            self.repl.console.print("[yellow]Nothing to purge.[/yellow]")
            return

        if tools is not None:
            tools_str = ", ".join(tools)
            confirm_msg = f"Delete all {tools_str} findings?"
        elif keep_reports:
            confirm_msg = "Delete ALL findings?"
        else:
            confirm_msg = "Delete ALL findings and reports?"

        chat_note = ""
        if analysis.chat_count > 0:
            chat_note = f" Also deletes {analysis.chat_count} chat session(s)."
        self.repl.console.print(
            f"Found [bold]{analysis.chroma_count}[/bold] document(s).{chat_note} "
            f"{confirm_msg} {escape('[y/N]')} ",
            end="",
        )
        answer = input().strip().lower()
        if answer != "y":
            self.repl.console.print("[dim]Aborted.[/dim]")
            return

        delete_merged = False
        if tools is None:
            self.repl.console.print(
                "Also delete merged endpoint URL files"
                " (endpoints/<repo>/merged_oas3.json, merged_urls.txt)"
                f" and clear merged path config? {escape('[y/N]')} ",
                end="",
            )
            delete_merged = input().strip().lower() == "y"

        result = service.execute(tools, keep_reports, delete_merged)

        self.repl.console.print(
            f"[green]Deleted {result.chroma_deleted} document(s).[/green]"
        )
        if result.chat_deleted > 0:
            self.repl.console.print(
                f"[green]Deleted {result.chat_deleted} chat session(s).[/green]"
            )

    # Private helpers

    def _resolve_project_id(self) -> int | None:
        """Resolve the active project's id via the registry, or None on miss."""
        assert self.repl.active_project is not None
        try:
            row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        except Exception:
            return None
        if row is None:
            return None
        return row.id

    def _get_knowledge_base(self) -> FindingKnowledgeBase:
        """Return the per-project knowledge base.

        Raises ``RagUnavailable`` when the embedding provider, LLM
        provider, or vector index cannot be constructed.
        """
        assert self.repl.active_project is not None
        kb = get_or_build_knowledge_base(
            self.repl.knowledge_base_cache,
            self.repl.active_project,
            self.repl.base_path,
        )
        if kb is None:
            raise RagUnavailable(
                "RAG engine unavailable for this project; "
                "ChromaDB or embedding provider is not reachable"
            )
        return kb
