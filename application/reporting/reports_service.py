"""Application service for reports and drafts."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

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
from core.config.manager import ConfigManager
from domain.reports.draft_summary import DraftSectionSummary

if TYPE_CHECKING:
    from application.ports.draft_event_sink import DraftEventSink
    from application.ports.draft_files import DraftFilesPort
    from application.ports.draft_repository import DraftRepositoryPort
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.ports.report_repository import ReportRepositoryPort
    from application.ports.user_prompt import UserPromptPort


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
    diagnostics only; the worker releases the lock, not the caller.
    """

    sections: tuple[str, ...]
    holder_token: str


class ReportsService:
    """Reports + drafts facade bound to a single project."""

    def __init__(
        self,
        report_repo: ReportRepositoryPort,
        draft_repo: DraftRepositoryPort,
        finding_repo: FindingRepositoryPort,
        repo_repo: ProjectRepoRepositoryPort,
        *,
        draft_files: DraftFilesPort | None = None,
        lock_registry: LockRegistry | None = None,
        draft_run_registry: DraftRunRegistry | None = None,
    ) -> None:
        self._report_repo = report_repo
        self._draft_repo = draft_repo
        self._draft_files = draft_files
        self._finding_repo = finding_repo
        self._repo_repo = repo_repo
        self._lock_registry = lock_registry or get_registry()
        self._draft_run_registry = draft_run_registry or get_draft_run_registry()

    @property
    def report_repo(self) -> ReportRepositoryPort:
        return self._report_repo

    @property
    def draft_repo(self) -> DraftRepositoryPort:
        return self._draft_repo

    @property
    def draft_files(self) -> DraftFilesPort | None:
        return self._draft_files

    def get_section_summary(self, section: str) -> DraftSectionSummary:
        """Build a summary for a single draft section."""
        record = self._draft_repo.get(section)
        text = (
            self._draft_files.read(section)
            if self._draft_files
            else self._draft_repo.read_content(section)
        )
        word_count: int | None = None
        preview: str | None = None
        if text is not None:
            word_count = len(text.split())
            preview = text[:200]
        return DraftSectionSummary(
            section=section,
            status=record.status if record else "not_generated",
            generated_at=record.generated_at if record else None,
            reviewed_at=record.reviewed_at if record else None,
            uploaded_filename=record.original_filename if record else None,
            word_count=word_count,
            preview=preview,
            error=record.error if record else None,
        )

    def write_draft(self, section: str, content: str) -> None:
        """Write draft content via the filesystem port."""
        if self._draft_files:
            self._draft_files.write(section, content)

    def read_draft(self, section: str) -> str | None:
        """Read draft content via the filesystem port."""
        if self._draft_files:
            return self._draft_files.read(section)
        return None

    def draft_exists(self, section: str) -> bool:
        """Check if a draft file exists via the filesystem port."""
        if self._draft_files:
            return self._draft_files.exists(section)
        return False

    def delete_draft_file(self, section: str) -> None:
        """Delete a draft file via the filesystem port."""
        if self._draft_files:
            self._draft_files.delete(section)

    @staticmethod
    def resolve_output_path(
        output_path: str | None,
        fmt: str,
        reports_dir: Path,
    ) -> Path:
        """Resolve a user-provided output path or generate a timestamped fallback."""
        reports_dir_resolved = reports_dir.resolve()
        if output_path:
            p = Path(output_path)
            if not p.is_absolute():
                resolved = (reports_dir / p).resolve()
            else:
                resolved = p.resolve()
            return resolved
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        ext = "md" if fmt == "markdown" else fmt
        return reports_dir_resolved / f"report_{ts}.{ext}"

    @staticmethod
    def get_retention_count(base_path: str) -> int:
        """Read report_retention_count from global config, default 10."""
        try:
            config = ConfigManager(base_path).global_config
            return int(getattr(config, "report_retention_count", 10) or 0)
        except FileNotFoundError:
            return 10

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
                        finding_repo=self._finding_repo,
                        repo_repo=self._repo_repo,
                        event_sink=event_sink,
                        cancel_token=cancel_token,
                        draft_files=self._draft_files,
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
