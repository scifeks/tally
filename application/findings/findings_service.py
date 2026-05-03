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
from typing import TYPE_CHECKING, Any, Self

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
from core.project_paths import ProjectPaths
from domain.findings.events import FindingUpdated
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.finding_history import (
    FindingHistoryRepository,
)
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import RepositoryRepository

if TYPE_CHECKING:
    from application.ports.finding_history_repository import (
        FindingHistoryRepositoryPort,
    )
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.project.registry_service import ProjectRegistryService
    from application.rag.knowledge_base import FindingKnowledgeBase
    from domain.findings.entry import Finding


logger = logging.getLogger("application.findings_service")


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class FindingsService:
    """Findings-feature facade bound to a single project."""

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
        factory: ConnectionFactory | None = None,
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
        # Stored so :meth:`purge_all_findings_data` can call
        # ``factory.purge_non_preserved_tables()`` without re-resolving
        # the project. Optional in the constructor so existing test
        # fixtures that build the service from stubs remain valid.
        self._factory = factory
        self._kb_cache: dict[str, FindingKnowledgeBase | None] = (
            knowledge_base_cache if knowledge_base_cache is not None else {}
        )
        self._base_path = base_path
        self._event_sink: FindingEventSink = event_sink or NullFindingEventSink()

    @classmethod
    def for_project(
        cls,
        registry: ProjectRegistryService,
        project_id: int,
        *,
        knowledge_base_cache: dict[str, FindingKnowledgeBase | None] | None = None,
        base_path: str | None = None,
        event_sink: FindingEventSink | None = None,
    ) -> Self:
        row = registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
            raise ProjectNotFound(f"project {project_id} not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        # Capture before init_schema(): init creates the file, and
        # repo_name_lookup needs to know whether the project has any
        # persisted findings yet.
        findings_db_exists = paths.findings_db.exists()
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        finding_repo = FindingRepository(factory)
        history_repo = FindingHistoryRepository(factory)
        project_repo = RepositoryRepository(factory)
        analyst = FindingAnalystService(finding_repo)
        return cls(
            finding_repo=finding_repo,
            history_repo=history_repo,
            project_repo=project_repo,
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=project_id,
            project_name=row.name,
            findings_db_exists=findings_db_exists,
            factory=factory,
            knowledge_base_cache=knowledge_base_cache,
            base_path=base_path or "",
            event_sink=event_sink,
        )

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
        """Wipe every non-preserved table in the project's findings DB.

        Used by the full ``purge`` REPL command. The ``repositories``
        table is preserved by ``ConnectionFactory.purge_non_preserved_tables``;
        every other findings-DB table is cleared. Failures are
        swallowed so the REPL flow can proceed with the rest of the
        purge cascade; the caller prints a warning if it cares.
        """
        if self._factory is None:
            return
        try:
            self._factory.purge_non_preserved_tables()
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
