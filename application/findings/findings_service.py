"""Application service for findings persistence + analyst access.

Owns per-request construction of repos so routes avoid direct imports
of infrastructure persistence. Composes ``FindingAnalystService`` and
exposes history repo + ``repo_name_lookup`` helper. Owns the
``patch_finding`` / ``batch_patch_findings`` orchestration: lock holder
construction, ChromaDB best-effort sync, and ``FindingUpdated`` event
emission via the injected sink.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from application.findings.analyst_service import (
    BulkUpdateResult,
    FindingAnalystService,
)
from application.locking import LockQueryService
from application.ports.finding_event_sink import (
    FindingEventSink,
    NullFindingEventSink,
)
from application.rag.ingestor import ToolHandlerFactory
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from domain.findings.events import FindingUpdated

if TYPE_CHECKING:
    from collections.abc import Callable

    from application.ports.finding_history_repository import (
        FindingHistoryRepositoryPort,
    )
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.rag.knowledge_base import FindingKnowledgeBase
    from domain.findings.entry import Finding


logger = logging.getLogger("application.findings_service")


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class FindingsService:
    """Findings feature facade bound to a single project."""

    def __init__(
        self,
        finding_repo: FindingRepositoryPort,
        history_repo: FindingHistoryRepositoryPort,
        project_repo: ProjectRepoRepositoryPort,
        analyst: FindingAnalystService,
        lock_query: LockQueryService,
        *,
        project_id: int,
        project_name: str,
        findings_db_exists: bool,
        purge_tables: Callable[[], None] | None = None,
        knowledge_base_cache: dict[str, FindingKnowledgeBase | None] | None = None,
        base_path: str = "",
        event_sink: FindingEventSink | None = None,
    ) -> None:
        self._finding_repo = finding_repo
        self._history_repo = history_repo
        self._project_repo = project_repo
        self._analyst = analyst
        self._lock_query = lock_query
        self._project_id = project_id
        self._project_name = project_name
        self._findings_db_exists = findings_db_exists
        self._purge_tables = purge_tables
        self._kb_cache: dict[str, FindingKnowledgeBase | None] = (
            knowledge_base_cache if knowledge_base_cache is not None else {}
        )
        self._base_path = base_path
        self._event_sink: FindingEventSink = event_sink or NullFindingEventSink()

    @property
    def analyst(self) -> FindingAnalystService:
        return self._analyst

    @property
    def finding_repo(self) -> FindingRepositoryPort:
        return self._finding_repo

    @property
    def history_repo(self) -> FindingHistoryRepositoryPort:
        return self._history_repo

    @property
    def project_id(self) -> int:
        return self._project_id

    @property
    def project_name(self) -> str:
        return self._project_name

    def repo_name_lookup(self) -> dict[int, str]:
        """Return {repo_id: repo_name} for active repos.

        Returns empty dict when the findings DB has not been created yet
        or when the underlying read raises.
        """
        if not self._findings_db_exists:
            return {}
        try:
            return {
                r.id: r.name
                for r in self._project_repo.list_active()
                if r.name and isinstance(r.id, int)
            }
        except Exception:
            return {}

    def lock_state_for(self, finding_id: int) -> tuple[bool, str | None]:
        """Return (is_locked, lock_holder) for a single finding."""
        return (
            self._lock_query.is_finding_locked(finding_id),
            self._lock_query.finding_lock_holder(finding_id),
        )

    def count_findings(self, *, tools: list[str] | None = None) -> int:
        """Total count of rows in the findings table.

        Returns 0 when the findings DB has not been created yet or
        when the underlying read raises. When *tools* is provided,
        the count is restricted to rows whose ``tool`` value is in
        the list.
        """
        if not self._findings_db_exists:
            return 0
        try:
            return self._finding_repo.count_findings(tools=tools)
        except Exception:
            return 0

    def delete_findings_for_tools(self, tools: list[str]) -> None:
        """Delete findings for the given tools.

        Empty list is a no-op. Failures swallowed so the REPL purge
        flow can continue with the url_findings cleanup; the caller
        prints a warning if it cares.
        """
        if not tools:
            return
        try:
            self._finding_repo.delete_findings(tools=tools)
        except Exception:
            return

    def purge_all_findings_data(self) -> None:
        """Clear operational tables in the project's findings DB.

        Configuration tables (repositories, tool_arg_profiles,
        tool_overrides, saved_scans) are preserved.
        """
        if self._purge_tables is None:
            return
        try:
            self._purge_tables()
        except Exception:
            return

    def patch_finding(self, finding_id: int, fields: dict[str, Any]) -> Finding | None:
        """Apply analyst-writable updates to a single finding.

        Acquires the per-finding lock under a service-built holder, writes
        the fields, syncs to ChromaDB best-effort, and emits a
        ``FindingUpdated`` event. Returns the refreshed ``Finding`` on
        success or ``None`` if the finding does not exist. Raises
        ``FindingsBusy`` if the finding is held by another holder.
        """
        holder = f"analyst-patch:{uuid.uuid4().hex[:8]}"
        updated = self._analyst.update_fields(finding_id, fields, holder_token=holder)
        if not updated:
            return None
        finding = self._analyst.get_finding(finding_id)
        if finding is None:
            return None
        self._sync_to_chroma(finding_id)
        self._emit_updated(finding)
        return finding

    def batch_patch_findings(
        self, ids: list[int], fields: dict[str, Any]
    ) -> BulkUpdateResult:
        """Apply analyst-writable updates to multiple findings.

        Per-id lock acquire / write / release; locked rows skipped, not
        errored. After the bulk write, each successfully updated row is
        synced to ChromaDB and an event is emitted. Returns the
        ``BulkUpdateResult`` from the analyst service unchanged.
        """
        holder = f"analyst-batch:{uuid.uuid4().hex[:8]}"
        result = self._analyst.bulk_update_fields(ids, fields, holder_token=holder)
        for fid in result.updated:
            finding = self._analyst.get_finding(fid)
            if finding is None:
                continue
            self._sync_to_chroma(fid)
            self._emit_updated(finding)
        return result

    def create_manual_finding(self, fields: dict[str, Any]) -> Finding:
        """Create a manually-reported finding."""
        from domain.findings.events import FindingCreated
        from domain.findings.manual import (
            derive_domain,
            manual_fingerprint,
        )
        from domain.findings.normalization import (
            normalise_cwe,
            normalise_finding_type,
            severity_to_rank,
        )
        from domain.tools.constants import (
            CONFIDENCE_LEVELS,
            SEVERITY_LEVELS,
            STATUS_LEVELS,
        )
        from domain.tools.scan_types import SEGMENT_ORDER

        title = fields.get("title")
        severity = fields.get("severity")
        segment = fields.get("segment")
        if not title:
            raise ValueError("title is required")
        if not severity:
            raise ValueError("severity is required")
        if severity not in SEVERITY_LEVELS:
            raise ValueError(f"severity must be one of {sorted(SEVERITY_LEVELS)}")
        if not segment or segment not in SEGMENT_ORDER:
            raise ValueError(f"segment must be one of {SEGMENT_ORDER}")

        file_val = fields.get("file")
        url_val = fields.get("url")
        repo_id_val = fields.get("repo_id")
        if not file_val and not url_val and not repo_id_val:
            raise ValueError(
                "At least one location field required (file, url, or repo_id)"
            )

        confidence = fields.get("confidence")
        if confidence and confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}")

        status = fields.get("status", "active")
        if status not in STATUS_LEVELS:
            raise ValueError(f"status must be one of {sorted(STATUS_LEVELS)}")

        domain = derive_domain(segment)
        location = file_val or url_val or str(repo_id_val)
        fingerprint = manual_fingerprint(title, segment, location)

        columns: dict[str, Any] = {
            "tool": "manual",
            "domain": domain,
            "segment": segment,
            "severity": severity_to_rank(severity),
            "confidence": confidence,
            "file": file_val,
            "url": url_val,
            "repo_id": repo_id_val,
            "vulnerability_id": fields.get("vulnerability_id"),
            "description": fields.get("description"),
            "status": status,
            "finding_type": normalise_finding_type(fields.get("finding_type")),
            "cwe": normalise_cwe(fields.get("cwe")),
        }

        meta: dict[str, Any] = {}
        if title:
            meta["title"] = title
        if fields.get("notes"):
            meta["notes"] = fields["notes"]

        fid = self._finding_repo.insert_manual_finding(columns, meta, fingerprint)

        finding = self._finding_repo.get_finding(fid)
        if finding is None:
            raise RuntimeError(f"Finding {fid} not found after insert")

        self._event_sink.emit(
            FindingCreated(
                project_id=self._project_id,
                finding=finding,
                is_locked=False,
                lock_holder=None,
            )
        )
        return finding

    def delete_manual_finding(self, finding_id: int) -> None:
        """Delete a manual finding by ID."""
        from application.locking import FindingsBusy
        from domain.findings.events import FindingDeleted

        finding = self._finding_repo.get_finding(finding_id)
        if finding is None:
            raise LookupError(f"Finding {finding_id} not found")

        if finding.tool != "manual":
            raise PermissionError("Only manual findings can be deleted")

        if self._lock_query.is_finding_locked(finding_id):
            holder = self._lock_query.finding_lock_holder(finding_id) or "unknown"
            raise FindingsBusy([finding_id], {finding_id: holder})

        self._finding_repo.delete_finding_by_id(finding_id)

        self._remove_from_chroma(finding_id)

        self._event_sink.emit(
            FindingDeleted(
                project_id=self._project_id,
                finding_id=finding_id,
            )
        )

    def _emit_updated(self, finding: Finding) -> None:
        is_locked, lock_holder = self.lock_state_for(finding.id)
        self._event_sink.emit(
            FindingUpdated(
                project_id=self._project_id,
                finding=finding,
                is_locked=is_locked,
                lock_holder=lock_holder,
            )
        )

    def _sync_to_chroma(self, finding_id: int) -> None:
        """Best-effort ChromaDB upsert after a SQLite analyst PATCH.

        Fetches the row, renders text via ``ToolHandler.render()``, and
        upserts via the per-project knowledge base. Never raises; all
        exceptions are caught and logged as warnings.
        """
        try:
            knowledge_base = get_or_build_knowledge_base(
                self._kb_cache, self._project_name, self._base_path
            )
            if knowledge_base is None:
                logger.warning("Chroma sync: knowledge base not available; skipping")
                return

            rows = self._finding_repo.get_by_ids([finding_id])
            if not rows:
                logger.warning(
                    "Chroma sync: finding id=%s not found in SQLite (skipping)",
                    finding_id,
                )
                return

            row = rows[0]
            handler = ToolHandlerFactory.load(row["tool"])
            if handler is None:
                logger.warning(
                    "Chroma sync: no handler for tool=%s (finding id=%s) (skipping)",
                    row["tool"],
                    finding_id,
                )
                return

            text = handler.render(row)
            metadata = {"tool": row["tool"], "profile": row["profile"]}
            knowledge_base.add_findings(
                documents=[text],
                metadatas=[metadata],
                ids=[str(row["id"])],
            )
        except Exception as exc:
            logger.warning(
                "Chroma sync: unexpected error for finding id=%s: %s",
                finding_id,
                exc,
            )

    def _remove_from_chroma(self, finding_id: int) -> None:
        """Best-effort ChromaDB removal after a manual finding delete."""
        try:
            knowledge_base = get_or_build_knowledge_base(
                self._kb_cache,
                self._project_name,
                self._base_path,
            )
            if knowledge_base is None:
                return
            knowledge_base._index.delete(ids=[str(finding_id)])
        except Exception as exc:
            logger.warning(
                "Chroma cleanup: error for finding id=%s: %s",
                finding_id,
                exc,
            )
