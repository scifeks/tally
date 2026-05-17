"""Purge service: domain logic for deleting findings and artifacts."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from application.chat.sealing import purge_chat_for_project
from application.ports.filters import Eq
from application.purge.models import PurgeAnalysis, PurgeResult
from domain.tools.constants import URL_PRODUCING_TOOLS
from factories.persistence import (
    create_chat_session_service,
    create_findings_service,
    create_url_list_service,
)

if TYPE_CHECKING:
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.rag.knowledge_base import FindingKnowledgeBase
    from core.project_paths import ProjectPaths


class PurgeService:
    """Encapsulates all purge business logic for a project."""

    def __init__(
        self,
        knowledge_base: FindingKnowledgeBase,
        project_paths: ProjectPaths,
        project_registry: ProjectRegistryService,
        project_id: int,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.project_paths = project_paths
        self.project_registry = project_registry
        self.project_id = project_id

    def analyze(
        self,
        tools: list[str] | None,
        keep_reports: bool,
    ) -> PurgeAnalysis:
        """Analyze what would be purged without executing."""
        chroma_count = self._count_matching(tools=tools)
        sqlite_count = self._count_sqlite_findings(tools=tools)
        has_outputs = self._has_tool_output_files(tools=tools)
        has_reports = tools is None and not keep_reports and self._has_report_files()
        chat_count = self._count_chat_sessions() if tools is None else 0
        url_count = self._count_url_findings() if tools is None else 0

        return PurgeAnalysis(
            chroma_count=chroma_count,
            sqlite_count=sqlite_count,
            has_tool_outputs=has_outputs,
            has_reports=has_reports,
            chat_count=chat_count,
            url_count=url_count,
        )

    def execute(
        self,
        tools: list[str] | None,
        keep_reports: bool,
        delete_merged: bool,
    ) -> PurgeResult:
        """Execute the purge and return results."""
        chroma_deleted = 0
        if tools is not None:
            for t in tools:
                chroma_deleted += self.knowledge_base.delete_findings(tool=t)
        else:
            chroma_deleted = self.knowledge_base.delete_findings(tool=None)

        self._delete_tool_output_files(tools=tools)
        chat_deleted = self._purge_chat() if tools is None else 0
        self._purge_sqlite(tools=tools)
        reports_deleted = tools is None and not keep_reports
        if reports_deleted:
            self._delete_reports()
        merged_deleted = delete_merged
        if delete_merged:
            self._delete_merged_endpoints()

        return PurgeResult(
            chroma_deleted=chroma_deleted,
            chat_deleted=chat_deleted,
            reports_deleted=reports_deleted,
            merged_deleted=merged_deleted,
        )

    # Private helpers

    def _delete_tool_output_files(self, tools: list[str] | None) -> None:
        """Delete files from tool_outputs directories.

        If tools is given, delete all files in tool_outputs/<tool>/ for each
        tool. If tools is None, delete files in all tool_outputs subdirs.
        """
        tool_outputs_dir = self.project_paths.tool_outputs_dir
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
        """Delete all files and subdirectories inside the project reports/."""
        reports_dir = self.project_paths.reports_dir
        if not reports_dir.exists():
            return
        for item in reports_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    def _delete_merged_endpoints(self) -> None:
        """Empty each repo's endpoints directory of stale merged artifacts."""
        endpoints_dir = self.project_paths.endpoints_dir
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
        tool_outputs_dir = self.project_paths.tool_outputs_dir
        if not tool_outputs_dir.exists():
            return False
        if tools is not None:
            dirs_to_check = [tool_outputs_dir / t for t in tools]
        else:
            dirs_to_check = [d for d in tool_outputs_dir.iterdir() if d.is_dir()]
        return any(d.exists() and any(d.iterdir()) for d in dirs_to_check)

    def _has_report_files(self) -> bool:
        """Return True if the reports/ directory has any content."""
        reports_dir = self.project_paths.reports_dir
        if not reports_dir.exists():
            return False
        return any(reports_dir.iterdir())

    def _count_sqlite_findings(self, tools: list[str] | None) -> int:
        """Count SQLite findings matching the given tools, or total if None."""
        try:
            svc = create_findings_service(
                self.project_registry,
                self.project_id,
            )
            return svc.count_findings(tools=tools)
        except Exception:
            return 0

    def _count_url_findings(self) -> int:
        """Count url_findings rows for the active project (full-purge guard)."""
        try:
            svc = create_url_list_service(
                self.project_registry,
                self.project_id,
            )
            return svc.count_all_url_findings()
        except Exception:
            return 0

    def _count_matching(
        self,
        tools: list[str] | None,
    ) -> int:
        """Return the count of documents that match the given filters."""
        if tools is not None:
            total = 0
            for t in tools:
                try:
                    total += self.knowledge_base.count(Eq("tool", t))
                except Exception:
                    pass
            return total

        return self.knowledge_base.count()

    def _count_chat_sessions(self) -> int:
        """Return the chat session count for the active project."""
        try:
            svc = create_chat_session_service(
                self.project_registry,
                self.project_id,
            )
            return len(
                svc.session_repo.list_for_project(self.project_id, include_expired=True)
            )
        except Exception:
            return 0

    def _purge_chat(self) -> int:
        """Hard-delete every chat session for the active project.

        Returns the number of sessions deleted. Failures swallowed.
        """
        try:
            svc = create_chat_session_service(
                self.project_registry,
                self.project_id,
            )
            return purge_chat_for_project(
                self.project_id, session_repo=svc.session_repo
            )
        except Exception:
            return 0

    def _purge_sqlite(self, tools: list[str] | None) -> None:
        """Delete SQLite findings for the given tools, or full wipe if None.

        Key domain rule: when tools is not None, URL findings are only
        deleted for tools in URL_PRODUCING_TOOLS.
        """
        try:
            findings = create_findings_service(self.project_registry, self.project_id)
            urls = create_url_list_service(self.project_registry, self.project_id)
            if tools is None:
                urls.purge_all_url_findings()
                findings.purge_all_findings_data()
            else:
                findings.delete_findings_for_tools(tools)
                url_tools = [t for t in tools if t in URL_PRODUCING_TOOLS]
                if url_tools:
                    urls.delete_url_findings_for_tools(url_tools)
        except Exception:
            pass
