"""Purge command: delete findings from the knowledge base."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from rich.markup import escape

from application.ports.filters import Eq
from application.tools.registry import tool_registry
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
            known = set(tool_registry.list_tool_names())
            invalid = [t for t in tools if t not in known]
            if invalid:
                self.repl.console.print(
                    f"[red]Unknown tool(s):[/red] {', '.join(invalid)}\n"
                    f"Configured tools: {', '.join(sorted(known))}"
                )
                return

        kb = self._get_knowledge_base()
        if kb is None:
            return

        count = self._count_matching(kb, tools=tools)
        sqlite_count = self._count_sqlite_findings(tools=tools)
        has_outputs = self._has_tool_output_files(tools=tools)
        has_reports = tools is None and not keep_reports and self._has_report_files()
        # Chat purge runs only on the full-purge path (no --tool filter).
        chat_count = self._count_chat_sessions() if tools is None else 0
        url_count = self._count_url_findings() if tools is None else 0

        if (
            count == 0
            and sqlite_count == 0
            and not has_outputs
            and not has_reports
            and chat_count == 0
            and url_count == 0
        ):
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

        chat_note = ""
        if chat_count > 0:
            chat_note = f" Also deletes {chat_count} chat session(s)."
        self.repl.console.print(
            f"Found [bold]{count}[/bold] document(s).{chat_note} "
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

        total_deleted = 0
        if tools is not None:
            for t in tools:
                total_deleted += kb.delete_findings(tool=t)
        else:
            total_deleted = kb.delete_findings(tool=None)
        self._delete_tool_output_files(tools=tools)
        # Chat purge runs before _purge_sqlite. Full-wipe deletes the
        # findings.db file outright, so going through the chat helper
        # first keeps the explicit application-layer semantics regardless
        # of how the SQLite wipe is done.
        chat_deleted = self._purge_chat() if tools is None else 0
        self._purge_sqlite(tools=tools)
        if tools is None and not keep_reports:
            self._delete_reports()
        if delete_merged:
            self._delete_merged_endpoints()
        self.repl.console.print(f"[green]Deleted {total_deleted} document(s).[/green]")
        if chat_deleted > 0:
            self.repl.console.print(
                f"[green]Deleted {chat_deleted} chat session(s).[/green]"
            )

    # Private helpers

    def _delete_tool_output_files(self, tools: list[str] | None) -> None:
        """Delete files from tool_outputs directories.

        If tools is given, delete all files in tool_outputs/<tool>/ for each tool.
        If tools is None, delete files in all tool_outputs subdirs (keep dirs).
        """
        tool_outputs_dir = _project_paths(self.repl).tool_outputs_dir
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
        reports_dir = _project_paths(self.repl).reports_dir
        if not reports_dir.exists():
            return
        for item in reports_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    def _delete_merged_endpoints(self) -> None:
        """Empty each repo's endpoints directory.

        Phase 9 dropped the JSON-side ``merged_seeds_path`` /
        ``merged_oas3_path`` fields; the merged artifacts are now
        JIT-rebuilt from ``url_findings`` rows, so the only cleanup
        needed here is removing any stale on-disk files.
        """
        assert self.repl.active_project is not None
        endpoints_dir = _project_paths(self.repl).endpoints_dir
        if not endpoints_dir.exists():
            return
        for repo_dir in endpoints_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            for item in repo_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    def _has_tool_output_files(self, tools: list[str] | None) -> bool:
        """Return True if any files exist in the relevant tool_outputs dirs."""
        tool_outputs_dir = _project_paths(self.repl).tool_outputs_dir
        if not tool_outputs_dir.exists():
            return False
        if tools is not None:
            dirs_to_check = [tool_outputs_dir / t for t in tools]
        else:
            dirs_to_check = [d for d in tool_outputs_dir.iterdir() if d.is_dir()]
        return any(d.exists() and any(d.iterdir()) for d in dirs_to_check)

    def _has_report_files(self) -> bool:
        """Return True if the reports/ directory has any content."""
        reports_dir = _project_paths(self.repl).reports_dir
        if not reports_dir.exists():
            return False
        return any(reports_dir.iterdir())

    def _count_sqlite_findings(self, tools: list[str] | None) -> int:
        """Count SQLite findings matching the given tools, or total if None."""
        try:
            from infrastructure.store.connection import ConnectionFactory

            db_path = _project_paths(self.repl).findings_db
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

    def _count_url_findings(self) -> int:
        """Count url_findings rows for the active project (full-purge guard)."""
        try:
            from infrastructure.store.connection import ConnectionFactory

            db_path = _project_paths(self.repl).findings_db
            if not db_path.exists():
                return 0
            factory = ConnectionFactory(db_path)
            with factory.connect() as conn:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='url_findings'"
                )
                if cur.fetchone() is None:
                    return 0
                row = conn.execute("SELECT COUNT(*) FROM url_findings").fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def _count_matching(
        self,
        kb: FindingKnowledgeBase,
        tools: list[str] | None,
    ) -> int:
        """Return the count of documents that match the given filters."""
        if tools is not None:
            total = 0
            for t in tools:
                try:
                    total += kb.count(Eq("tool", t))
                except Exception:
                    pass
            return total

        return kb.count()

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

    def _count_chat_sessions(self) -> int:
        """Return the chat session count for the active project, or 0 on error."""
        project_id = self._resolve_project_id()
        if project_id is None:
            return 0
        try:
            from infrastructure.store.connection import ConnectionFactory
            from infrastructure.store.repositories.chat_sessions import (
                ChatSessionRepository,
            )

            db_path = _project_paths(self.repl).findings_db
            if not db_path.exists():
                return 0
            factory = ConnectionFactory(db_path)
            factory.init_schema()
            repo = ChatSessionRepository(factory)
            return len(repo.list_for_project(project_id, include_expired=True))
        except Exception:
            return 0

    def _purge_chat(self) -> int:
        """Hard-delete every chat session for the active project.

        Returns the number of sessions deleted. Failures are surfaced as
        a warning; the rest of the purge continues.
        """
        project_id = self._resolve_project_id()
        if project_id is None:
            return 0
        try:
            from application.chat.sealing import purge_chat_for_project
            from infrastructure.store.connection import ConnectionFactory
            from infrastructure.store.repositories.chat_sessions import (
                ChatSessionRepository,
            )

            paths = _project_paths(self.repl)
            factory = ConnectionFactory(paths.findings_db)
            factory.init_schema()
            session_repo = ChatSessionRepository(factory)
            return purge_chat_for_project(project_id, session_repo=session_repo)
        except Exception as exc:
            self.repl.console.print(f"[yellow]Chat purge warning:[/yellow] {exc}")
            return 0

    def _purge_sqlite(self, tools: list[str] | None) -> None:
        """Delete SQLite findings for the given tools, or full wipe if None."""
        try:
            from infrastructure.store.connection import ConnectionFactory
            from infrastructure.store.repositories.findings import FindingRepository

            db_path = _project_paths(self.repl).findings_db
            factory = ConnectionFactory(db_path)
            if tools is None:
                if factory.db_path.exists():
                    try:
                        from application.url_inventory.service import (
                            UrlInventoryService,
                        )
                        from infrastructure.store.repositories.url_findings import (
                            UrlFindingRepository,
                        )

                        UrlInventoryService(
                            UrlFindingRepository(factory)
                        ).delete_for_project()
                    except Exception:
                        pass
                    factory.purge_non_preserved_tables()
                else:
                    factory.init_schema()
            else:
                _URL_TOOLS = {"katana", "noir"}
                url_tools = [t for t in tools if t in _URL_TOOLS]
                if url_tools and factory.db_path.exists():
                    try:
                        placeholders = ",".join("?" * len(url_tools))
                        with factory.connect() as conn:
                            conn.execute(
                                f"DELETE FROM url_findings WHERE tool IN "
                                f"({placeholders})",
                                url_tools,
                            )
                    except Exception:
                        pass
                FindingRepository(factory).delete_findings(tools=tools)
        except Exception as exc:
            self.repl.console.print(f"[yellow]SQLite purge warning:[/yellow] {exc}")

    def _get_knowledge_base(self) -> FindingKnowledgeBase | None:
        """Build a FindingKnowledgeBase for the active project, or None on error."""
        from pathlib import Path

        from application.rag.knowledge_base import FindingKnowledgeBase
        from infrastructure.embedding.factory import get_embedding_provider
        from infrastructure.llm.factory import get_llm_provider
        from infrastructure.vector.factory import make_chromadb_vector_index

        assert self.repl.active_project is not None
        base = Path(self.repl.base_path)
        try:
            embedding_provider = get_embedding_provider(base)
            chat_provider = get_llm_provider("chat", base)
            vector_index = make_chromadb_vector_index(
                project_name=self.repl.active_project,
                base_path=base,
                embedding_provider=embedding_provider,
            )
            return FindingKnowledgeBase(
                vector_index=vector_index,
                chat_provider=chat_provider,
                project_name=self.repl.active_project,
                base_path=base,
            )
        except RuntimeError as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
            return None
        except ValueError as exc:
            self.repl.console.print(f"[red]Project error:[/red] {exc}")
            return None
