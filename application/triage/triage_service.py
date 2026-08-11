"""Application service for triage: persistence facade and job orchestration."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.events.ids import new_event_id
from application.events.types import BusEvent
from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.sync.integration_sync import run_configured_syncs
from application.triage.factory import ensure_triage_backend_configured
from application.triage.orchestrator import (
    resume_triage_for_project,
    run_triage_for_project,
)
from application.triage.run_registry import (
    TriageRunRegistry,
    get_triage_run_registry,
)
from application.triage.runner import NoScanRunError, TriageCancelled
from core.config.manager import ConfigManager

if TYPE_CHECKING:
    from application.ports.audit_repository import AuditRepositoryPort
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_batch_repository import TriageBatchRepositoryPort
    from application.ports.triage_event_sink import TriageEventSink
    from application.tools.registry import ToolRegistry
    from domain.triage.entry import TriageBatchRow


logger = logging.getLogger("application.triage_service")

TRIAGE_LOCK_KIND = "triage"

_RESUMABLE_STATUSES = ("failed", "running")


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class TriageNotResumableError(RuntimeError):
    """Raised when resume_triage is called against a non-resumable run.

    Carries ``status`` for the route layer's 409 error payload.
    """

    def __init__(self, scan_run_id: int, status: str | None) -> None:
        super().__init__(
            f"triage scan_run_id {scan_run_id} is not resumable (status={status!r})"
        )
        self.scan_run_id = scan_run_id
        self.status = status


@dataclass(frozen=True)
class TriageStartHandle:
    """Handle returned from start_triage/resume_triage.

    ``scan_run_id`` and ``holder_token`` are available immediately;
    ``result`` resolves with the orchestrator's outcome dict or exception.
    """

    scan_run_id: int
    holder_token: str
    result: Future[dict[str, int]]


class TriageService:
    """Triage facade bound to a single project."""

    def __init__(
        self,
        run_repo: RunRepositoryPort,
        triage_repo: TriageBatchRepositoryPort,
        finding_repo: FindingRepositoryPort,
        audit_repo: AuditRepositoryPort,
        *,
        repo_paths: dict[str, Path] | None = None,
        lock_registry: LockRegistry | None = None,
        triage_run_registry: TriageRunRegistry | None = None,
    ) -> None:
        self._run_repo = run_repo
        self._triage_repo = triage_repo
        self._finding_repo = finding_repo
        self._audit_repo = audit_repo
        self._repo_paths = repo_paths or {}
        self._lock_registry = lock_registry or get_registry()
        self._triage_run_registry = triage_run_registry or get_triage_run_registry()

    @property
    def run_repo(self) -> RunRepositoryPort:
        return self._run_repo

    @property
    def triage_repo(self) -> TriageBatchRepositoryPort:
        return self._triage_repo

    # Use cases

    def start_triage(
        self,
        *,
        base_path: str,
        project_id: int,
        project_name: str,
        tool_registry: ToolRegistry,
        event_sink: TriageEventSink | None = None,
        finding_ids: tuple[int, ...] | None = None,
        scan_run_id: int | None = None,
    ) -> TriageStartHandle:
        """Start a triage run against the latest scan_run for a project.

        Raises NoScanRunError if no scan_runs exist, JobBusy if another
        triage holds the lock.
        """
        del finding_ids  # finding-scoped triage is reserved for later
        ensure_triage_backend_configured(app_root=Path(base_path))
        if scan_run_id is None:
            scan_run_id = self._run_repo.latest_run_id()
        if scan_run_id is None:
            raise NoScanRunError(
                f"No scan runs found for project {project_name!r}; "
                "run a scan before triage"
            )
        return self._dispatch(
            base_path=base_path,
            project_id=project_id,
            project_name=project_name,
            scan_run_id=scan_run_id,
            tool_registry=tool_registry,
            event_sink=event_sink,
            is_resume=False,
        )

    def resume_triage(
        self,
        *,
        base_path: str,
        project_id: int,
        project_name: str,
        scan_run_id: int,
        tool_registry: ToolRegistry,
        event_sink: TriageEventSink | None = None,
    ) -> TriageStartHandle:
        """Resume an existing triage run for a project.

        Raises TriageNotResumableError if the run does not exist or is in
        a terminal state, JobBusy if another triage holds the lock.
        """
        ensure_triage_backend_configured(app_root=Path(base_path))
        summary = self._triage_repo.summarize_for_run(scan_run_id)
        if summary is None:
            raise TriageNotResumableError(scan_run_id, status=None)
        if summary.status not in _RESUMABLE_STATUSES:
            raise TriageNotResumableError(scan_run_id, status=summary.status)
        return self._dispatch(
            base_path=base_path,
            project_id=project_id,
            project_name=project_name,
            scan_run_id=scan_run_id,
            tool_registry=tool_registry,
            event_sink=event_sink,
            is_resume=True,
        )

    def _dispatch(
        self,
        *,
        base_path: str,
        project_id: int,
        project_name: str,
        scan_run_id: int,
        tool_registry: ToolRegistry,
        event_sink: TriageEventSink | None,
        is_resume: bool,
    ) -> TriageStartHandle:
        holder_token = f"triage-run:{uuid.uuid4().hex[:8]}"
        self._lock_registry.acquire_job(TRIAGE_LOCK_KIND, holder_token)

        cancel_token = CancellationToken()
        try:
            self._triage_run_registry.register(
                scan_run_id=scan_run_id,
                project_id=project_id,
                cancel_token=cancel_token,
            )
        except Exception:
            self._lock_registry.release_job(TRIAGE_LOCK_KIND, holder_token)
            raise

        future: Future[dict[str, int]] = Future()
        thread = threading.Thread(
            target=self._run_worker,
            kwargs={
                "future": future,
                "holder_token": holder_token,
                "base_path": base_path,
                "project_id": project_id,
                "project_name": project_name,
                "scan_run_id": scan_run_id,
                "event_sink": event_sink,
                "tool_registry": tool_registry,
                "cancel_token": cancel_token,
                "is_resume": is_resume,
            },
            name=f"triage-run-{scan_run_id}",
            daemon=True,
        )
        thread.start()
        return TriageStartHandle(
            scan_run_id=scan_run_id,
            holder_token=holder_token,
            result=future,
        )

    def _run_worker(
        self,
        *,
        future: Future[dict[str, int]],
        holder_token: str,
        base_path: str,
        project_id: int,
        project_name: str,
        scan_run_id: int,
        event_sink: TriageEventSink | None,
        tool_registry: ToolRegistry,
        cancel_token: CancellationToken,
        is_resume: bool,
    ) -> None:
        sink = event_sink
        try:
            try:
                from application.triage.container import (
                    ensure_triage_containers,
                    ensure_triage_image,
                )

                ensure_triage_image(Path(base_path))
                ensure_triage_containers(
                    Path(base_path),
                    project_name,
                    repo_paths=self._repo_paths or None,
                )

                if is_resume:
                    result = resume_triage_for_project(
                        project_name,
                        project_id=project_id,
                        scan_run_id=scan_run_id,
                        tool_registry=tool_registry,
                        run_repo=self._run_repo,
                        finding_repo=self._finding_repo,
                        triage_repo=self._triage_repo,
                        audit_repo=self._audit_repo,
                        repo_paths=self._repo_paths,
                        event_sink=sink,
                        cancel_token=cancel_token,
                        app_root=Path(base_path),
                        holder_token=holder_token,
                    )
                else:
                    result = run_triage_for_project(
                        project_name,
                        project_id=project_id,
                        tool_registry=tool_registry,
                        run_repo=self._run_repo,
                        finding_repo=self._finding_repo,
                        triage_repo=self._triage_repo,
                        audit_repo=self._audit_repo,
                        repo_paths=self._repo_paths,
                        event_sink=sink,
                        cancel_token=cancel_token,
                        app_root=Path(base_path),
                        scan_run_id=scan_run_id,
                        holder_token=holder_token,
                    )
                future.set_result(result)
                try:
                    gc = ConfigManager(base_path).load_global_config()
                    run_configured_syncs(
                        base_path=base_path,
                        project_name=project_name,
                        run_id=scan_run_id,
                        sync_list=gc.post_triage_sync,
                    )
                except Exception:
                    logger.exception(
                        "post-triage sync failed for scan_run_id=%d",
                        scan_run_id,
                    )
            except TriageCancelled as exc:
                logger.info("triage scan_run_id=%d cancelled", scan_run_id)
                future.set_exception(exc)
            except NoScanRunError as exc:
                # Defensive: start_triage validated this before spawn.
                logger.warning(
                    "triage scan_run_id=%d aborted: no scan_runs exist",
                    scan_run_id,
                )
                future.set_exception(exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("triage scan_run_id=%d failed", scan_run_id)
                future.set_exception(exc)
        finally:
            self._triage_run_registry.unregister(scan_run_id)
            try:
                self._lock_registry.release_job(TRIAGE_LOCK_KIND, holder_token)
            except HolderMismatch:
                logger.warning(
                    "lock holder mismatch on triage scan_run_id=%d release",
                    scan_run_id,
                )
            except KeyError:
                logger.warning(
                    "triage lock already released for scan_run_id=%d",
                    scan_run_id,
                )
            try:
                from application.triage.container import (
                    teardown_triage_containers,
                )

                teardown_triage_containers(Path(base_path))
            except Exception:
                logger.debug(
                    "post-triage container teardown failed",
                    exc_info=True,
                )

    # Snapshot queries

    async def build_snapshot_event(
        self,
        project_id: int,
        scan_run_id: int | None,
    ) -> BusEvent:
        """Build the on-connect snapshot for a triage SSE stream."""
        payload: dict[str, Any] = {
            "project_id": project_id,
            "scan_run_id": scan_run_id,
        }
        if scan_run_id is not None:
            summary = await asyncio.to_thread(
                self._triage_repo.summarize_for_run, scan_run_id
            )
            if summary is not None:
                batches = await asyncio.to_thread(
                    self._triage_repo.list_for_run, scan_run_id
                )
                payload.update(
                    status=summary.status,
                    total_findings=summary.total_findings,
                    processed_findings=summary.processed_findings,
                    started_at=summary.started_at,
                    finished_at=summary.finished_at,
                    batches=[self._batch_to_dict(b) for b in batches],
                )
        else:
            active = self._triage_run_registry.list_for_project(project_id)
            payload["active_scan_run_ids"] = [h.scan_run_id for h in active]

        return BusEvent(
            event_id=new_event_id(),
            job_id="triage",
            stream="triage",
            event_type="snapshot",
            payload=payload,
            ts=datetime.now(UTC),
        )

    @staticmethod
    def _batch_to_dict(batch: TriageBatchRow) -> dict[str, Any]:
        """Convert a batch row to a payload-ready dict."""
        segment: str | None = None
        if batch.batch_data and isinstance(batch.batch_data[0], dict):
            segment = batch.batch_data[0].get("segment")
        return {
            "id": batch.id,
            "scan_run_id": batch.run_id,
            "segment": segment,
            "finding_ids": batch.finding_ids,
            "status": batch.status,
            "attempts": batch.run_attempts,
            "started_at": batch.started_at,
            "finished_at": batch.completed_at,
            "response_preview": None,
            "error": None,
        }
