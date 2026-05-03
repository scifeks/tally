"""Application service for the reports + drafts persistence surface.

Owns per-request construction of the report and draft repos so route
modules do not import infrastructure persistence directly. Also owns the
``start_drafts`` use case: lock acquisition, worker thread spawn, and
per-section cancellation token registration. Routes do not touch
``LockRegistry`` directly — they call ``start_drafts`` and translate the
domain exceptions to HTTP status codes.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.reporting.draft_orchestrator import (
    DraftCancelled,
    DraftOverwriteDenied,
    DraftRequest,
    run_draft,
)
from application.reporting.draft_run_registry import (
    DraftRunRegistry,
    get_draft_run_registry,
)
from application.reporting.drafts import SECTION_REGISTRY
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.drafts import DraftRepository
from infrastructure.store.repositories.reports import ReportRepository

if TYPE_CHECKING:
    from application.ports.draft_event_sink import DraftEventSink
    from application.ports.draft_repository import DraftRepositoryPort
    from application.ports.report_repository import ReportRepositoryPort
    from application.ports.user_prompt import UserPromptPort
    from application.project.registry_service import ProjectRegistryService


logger = logging.getLogger("application.reports_service")

REPORT_LOCK_KIND = "report"


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class UnknownSectionError(ValueError):
    """Raised when a draft batch contains an unknown or duplicate section."""


@dataclass(frozen=True)
class DraftBatchHandle:
    """Returned from :meth:`ReportsService.start_drafts`.

    ``sections`` is the validated, deduplicated list the worker will iterate.
    ``holder_token`` is the lock holder for the batch and is exposed for
    diagnostics; callers should not pass it back to release the lock — the
    worker does that.
    """

    sections: tuple[str, ...]
    holder_token: str


class ReportsService:
    """Reports + drafts facade bound to a single project."""

    def __init__(
        self,
        report_repo: ReportRepositoryPort,
        draft_repo: DraftRepositoryPort,
        *,
        lock_registry: LockRegistry | None = None,
        draft_run_registry: DraftRunRegistry | None = None,
    ) -> None:
        self._report_repo = report_repo
        self._draft_repo = draft_repo
        self._lock_registry = lock_registry or get_registry()
        self._draft_run_registry = draft_run_registry or get_draft_run_registry()

    @classmethod
    def for_project(
        cls,
        registry: ProjectRegistryService,
        project_id: int,
    ) -> Self:
        row = registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
            raise ProjectNotFound(f"project {project_id} not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        return cls(
            report_repo=ReportRepository(factory),
            draft_repo=DraftRepository(factory),
        )

    @property
    def report_repo(self) -> ReportRepositoryPort:
        return self._report_repo

    @property
    def draft_repo(self) -> DraftRepositoryPort:
        return self._draft_repo

    def start_drafts(
        self,
        *,
        sections: list[str],
        force: bool,
        base_path: str,
        project_id: int,
        project_name: str,
        prompt: UserPromptPort,
        event_sink: DraftEventSink,
        skip_triage: bool = False,
    ) -> DraftBatchHandle:
        """Start a sequential draft batch on a daemon worker thread.

        Raises:
            UnknownSectionError: ``sections`` is empty, contains duplicates,
                or names a section not in :data:`SECTION_REGISTRY`.
            JobBusy: another report or draft batch is already running.
        """
        validated = _validate_sections(sections)

        holder_token = f"draft-batch:{uuid.uuid4().hex[:8]}"
        self._lock_registry.acquire_job(REPORT_LOCK_KIND, holder_token)

        thread = threading.Thread(
            target=self._run_worker,
            kwargs={
                "sections": validated,
                "force": force,
                "skip_triage": skip_triage,
                "base_path": base_path,
                "project_id": project_id,
                "project_name": project_name,
                "holder_token": holder_token,
                "prompt": prompt,
                "event_sink": event_sink,
            },
            name=f"draft-batch-{project_id}",
            daemon=True,
        )
        thread.start()
        return DraftBatchHandle(sections=validated, holder_token=holder_token)

    def _run_worker(
        self,
        *,
        sections: tuple[str, ...],
        force: bool,
        skip_triage: bool,
        base_path: str,
        project_id: int,
        project_name: str,
        holder_token: str,
        prompt: UserPromptPort,
        event_sink: DraftEventSink,
    ) -> None:
        try:
            for section in sections:
                cancel_token = CancellationToken()
                self._draft_run_registry.register(
                    section=section,
                    project_id=project_id,
                    cancel_token=cancel_token,
                )
                request = DraftRequest(
                    project=project_name,
                    base_path=Path(base_path),
                    section=section,
                    force_overwrite=force,
                    skip_triage=skip_triage,
                    project_id=project_id,
                )
                try:
                    run_draft(
                        request,
                        prompt=prompt,
                        repo=self._draft_repo,
                        event_sink=event_sink,
                        cancel_token=cancel_token,
                    )
                except DraftCancelled:
                    logger.info("draft run %r cancelled", section)
                except DraftOverwriteDenied as exc:
                    logger.info("draft run %r overwrite denied: %s", section, exc)
                except Exception:
                    logger.exception("draft run %r failed", section)
                finally:
                    self._draft_run_registry.unregister(section)
        finally:
            try:
                self._lock_registry.release_job(REPORT_LOCK_KIND, holder_token)
            except HolderMismatch:
                logger.warning(
                    "lock holder mismatch on draft batch %r release", holder_token
                )
            except KeyError:
                logger.warning(
                    "report lock already released for draft batch %r", holder_token
                )


def _validate_sections(sections: list[str]) -> tuple[str, ...]:
    if not sections:
        raise UnknownSectionError("sections must not be empty")
    seen: set[str] = set()
    for section in sections:
        if section in seen:
            raise UnknownSectionError(f"duplicate section {section!r}")
        if section not in SECTION_REGISTRY:
            raise UnknownSectionError(f"unknown section {section!r}")
        seen.add(section)
    return tuple(sections)
