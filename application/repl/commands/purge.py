"""Purge command: delete findings from the knowledge base."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape

from application.tools.registry import tool_registry

if TYPE_CHECKING:
    from application.rag.engine import RAGEngine
    from application.repl.interface import REPL

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

    # ------------------------------------------------------------------
    # Command entry point
    # ------------------------------------------------------------------

    def cmd_purge(self, _cmd: str, args: list[str]) -> None:
        """purge [--tool=<tool,...>] [--keep-reports]  — delete findings."""
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
        sqlite_count = self._count_sqlite_findings(tools=tools)
        has_outputs = self._has_tool_output_files(tools=tools)
        has_reports = tools is None and not keep_reports and self._has_report_files()

        if count == 0 and sqlite_count == 0 and not has_outputs and not has_reports:
            self.repl.console.print("[yellow]Nothing to purge.[/yellow]")
            return

        # Build confirmation prompt
        if tools is not None:
            tools_str = ", ".join(tools)
            confirm_msg = f"Delete all {tools_str} findings?"
        elif keep_reports:
            confirm_msg = "Delete ALL findings?"
        else:
            confirm_msg = "Delete ALL findings and reports?"

        self.repl.console.print(
            f"Found [bold]{count}[/bold] document(s). {confirm_msg} {escape('[y/N]')} ",
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

        total_deleted = 0
        if tools is not None:
            for t in tools:
                total_deleted += rag_engine.delete_findings(tool=t)
        else:
            total_deleted = rag_engine.delete_findings(tool=None)
        self._delete_tool_output_files(tools=tools)
        self._purge_sqlite(tools=tools)
        if tools is None and not keep_reports:
            self._delete_reports()
        if delete_merged:
            self._delete_merged_endpoints()
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

    def _delete_reports(self) -> None:
        """Delete all files and subdirectories inside the project reports/ dir."""
        assert self.repl.active_project is not None
        reports_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "reports"
        )
        if not reports_dir.exists():
            return
        for item in reports_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    def _delete_merged_endpoints(self) -> None:
        """Empty each repo's merged-URL dir and clear merged path keys in config."""
        assert self.repl.active_project is not None
        endpoints_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "endpoints"
        )
        if endpoints_dir.exists():
            for repo_dir in endpoints_dir.iterdir():
                if not repo_dir.is_dir():
                    continue
                for item in repo_dir.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

        try:
            from core.config.manager import ConfigManager

            manager = ConfigManager(self.repl.base_path)
            repos = manager.load_repositories(self.repl.active_project)
            updated = [
                r.model_copy(update={"merged_seeds_path": "", "merged_oas3_path": ""})
                for r in repos
            ]
            manager.save_repositories(self.repl.active_project, updated)
        except Exception as exc:
            self.repl.console.print(
                f"[yellow]Warning: could not clear merged path config: {exc}[/yellow]"
            )

    def _has_tool_output_files(self, tools: list[str] | None) -> bool:
        """Return True if any files exist in the relevant tool_outputs dirs."""
        assert self.repl.active_project is not None
        tool_outputs_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "tool_outputs"
        )
        if not tool_outputs_dir.exists():
            return False
        if tools is not None:
            dirs_to_check = [tool_outputs_dir / t for t in tools]
        else:
            dirs_to_check = [d for d in tool_outputs_dir.iterdir() if d.is_dir()]
        return any(d.exists() and any(d.iterdir()) for d in dirs_to_check)

    def _has_report_files(self) -> bool:
        """Return True if the reports/ directory has any content."""
        assert self.repl.active_project is not None
        reports_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "reports"
        )
        if not reports_dir.exists():
            return False
        return any(reports_dir.iterdir())

    def _count_sqlite_findings(self, tools: list[str] | None) -> int:
        """Count SQLite findings matching the given tools, or total if None."""
        assert self.repl.active_project is not None
        try:
            from infrastructure.store.connection import ConnectionFactory

            db_path = (
                Path(self.repl.base_path)
                / "projects"
                / self.repl.active_project
                / "sqlite"
                / "findings.db"
            )
            if not db_path.exists():
                return 0
            factory = ConnectionFactory(db_path)
            with factory.connect() as conn:
                if tools is None:
                    row = conn.execute("SELECT COUNT(*) FROM findings").fetchone()
                else:
                    placeholders = ",".join("?" * len(tools))
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM findings WHERE tool IN ({placeholders})",
                        tools,
                    ).fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

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
