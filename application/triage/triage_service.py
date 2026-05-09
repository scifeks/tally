"""Application service for triage: persistence facade plus the
``start_triage`` / ``resume_triage`` entry points.

Owns the Tier-1 ``triage`` job lock end-to-end. Driving adapters
(REPL, HTTP) call ``start_triage`` / ``resume_triage`` and translate
``JobBusy`` / ``NoScanRunError`` / ``TriageNotResumableError`` to
their wire formats. The worker thread releases the lock in its
``finally``.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
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
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository

if TYPE_CHECKING:
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_batch_repository import TriageBatchRepositoryPort
    from application.ports.triage_event_sink import TriageEventSink
    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


logger = logging.getLogger("application.triage_service")

TRIAGE_LOCK_KIND = "triage"

_RESUMABLE_STATUSES = ("failed", "running")


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class TriageNotResumableError(RuntimeError):
    """Raised when ``resume_triage`` is called against a non-resumable run.

    Carries ``status`` so the route layer can include it in the 409
    error payload.
    """

    def __init__(self, scan_run_id: int, status: str | None) -> None:
        super().__init__(
            f"triage scan_run_id {scan_run_id} is not resumable (status={status!r})"
        )
        self.scan_run_id = scan_run_id
        self.status = status


@dataclass(frozen=True)
class TriageStartHandle:
    """Returned from :meth:`TriageService.start_triage`/``resume_triage``.

    ``scan_run_id`` and ``holder_token`` are available immediately.
    ``result`` resolves with the triage outcome dict produced by the
    orchestrator (``sessions_run`` / ``success`` / ``failed`` /
    ``incomplete``) when the worker thread completes, or with the
    raised exception on failure.
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
        *,
        lock_registry: LockRegistry | None = None,
        triage_run_registry: TriageRunRegistry | None = None,
    ) -> None:
        self._run_repo = run_repo
        self._triage_repo = triage_repo
        self._lock_registry = lock_registry or get_registry()
        self._triage_run_registry = triage_run_registry or get_triage_run_registry()

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
            run_repo=RunRepository(factory),
            triage_repo=TriageBatchRepository(factory),
        )

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
    ) -> TriageStartHandle:
        """Start a triage run against the latest scan_run for a project.

        Raises:
            NoScanRunError: project has no scan_runs to triage. The lock
                is not acquired in this case.
            JobBusy: another triage already holds the lock.
        """
        del finding_ids  # finding-scoped triage is reserved for later
        ensure_triage_backend_configured(app_root=Path(base_path))
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

        Raises:
            TriageNotResumableError: the run does not exist or is in a
                terminal state. The lock is not acquired in this case.
            JobBusy: another triage already holds the lock.
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
                if is_resume:
                    result = resume_triage_for_project(
                        project_name,
                        project_id=project_id,
                        scan_run_id=scan_run_id,
                        tool_registry=tool_registry,
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
                        event_sink=sink,
                        cancel_token=cancel_token,
                        app_root=Path(base_path),
                        scan_run_id=scan_run_id,
                        holder_token=holder_token,
                    )
                future.set_result(result)
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
