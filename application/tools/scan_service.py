"""Single core port for starting a scan."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import Future
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.ports.progress_reporter import ProgressReporter
from application.ports.scan_event_sink import ScanEventSink
from application.ports.user_prompt import UserPromptPort
from application.tools.executor import ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.orchestrator import ScanOrchestrator
from application.tools.scan_run_registry import ScanRunRegistry, get_scan_run_registry
from domain.pipeline import scan_events as se
from domain.tools.scan_types import ScanSummary
from infrastructure.tools.runner import SubprocessRunner

if TYPE_CHECKING:
    from application.ports.chat_session_repository import (
        ChatSessionRepositoryPort,
    )
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.tool_arg_profiles import (
        ToolArgProfilesRepositoryPort,
    )
    from application.tools.registry import ToolRegistry
    from domain.tools.display import DisplayProtocol


logger = logging.getLogger("application.scan_service")

SCAN_LOCK_KIND = "scan"


@dataclass(frozen=True)
class ScanHandle:
    """Returned from :meth:`ScanService.start_scan`.

    ``run_id`` is available immediately. ``result`` resolves when the
    background scan completes.
    """

    run_id: int
    result: Future[ScanSummary]


class ScanService:
    """Single core entry point for starting a scan."""

    def __init__(
        self,
        *,
        lock_registry: LockRegistry | None = None,
        scan_run_registry: ScanRunRegistry | None = None,
    ) -> None:
        self._lock_registry = lock_registry or get_registry()
        self._scan_run_registry = scan_run_registry or get_scan_run_registry()

    def start_scan(
        self,
        *,
        project_id: int,
        project_name: str,
        base_path: str,
        tool_registry: ToolRegistry,
        run_repo: RunRepositoryPort,
        chat_session_repo: ChatSessionRepositoryPort,
        profiles_repo: ToolArgProfilesRepositoryPort,
        repo_ids: tuple[str, ...] = (),
        tool_ids: tuple[str, ...] = (),
        domains: tuple[str, ...] = (),
        skip_tool_ids: tuple[str, ...] = (),
        skip_enrichment: bool = False,
        prompt: UserPromptPort,
        reporter: ProgressReporter | None = None,
        event_sink: ScanEventSink | None = None,
        display: DisplayProtocol | None = None,
        run_args: dict[str, Any] | None = None,
        arg_profile_ids: list[int] | None = None,
        saved_scan_id: int | None = None,
    ) -> ScanHandle:
        """Start a scan and return a :class:`ScanHandle`.

        Raises:
            JobBusy: another scan is already holding the scan slot.
            ValueError: ``arg_profile_ids`` references unknown profiles.
            Anything raised by ``run_repo.create``: the lock is released
                before the exception propagates.
        """
        holder_token = f"scan-run:{uuid.uuid4().hex[:8]}"
        self._lock_registry.acquire_job(SCAN_LOCK_KIND, holder_token)

        try:
            snapshots = _resolve_arg_profile_snapshots(profiles_repo, arg_profile_ids)
            run_id = run_repo.create(
                project_id=project_id,
                repo_ids=list(repo_ids),
                tool_ids=list(tool_ids),
                domains=list(domains),
                skip_enrichment=skip_enrichment,
                args=run_args,
                saved_scan_id=saved_scan_id,
            )
            for tool_name, snapshot_json in snapshots.items():
                run_repo.set_arg_profile_snapshot(run_id, tool_name, snapshot_json)
        except Exception:
            self._lock_registry.release_job(SCAN_LOCK_KIND, holder_token)
            raise

        cancel_token = CancellationToken()
        self._scan_run_registry.register(
            run_id=run_id,
            project_id=project_id,
            cancel_token=cancel_token,
        )

        future: Future[ScanSummary] = Future()
        thread = threading.Thread(
            target=self._run_worker,
            kwargs={
                "future": future,
                "holder_token": holder_token,
                "run_id": run_id,
                "project_id": project_id,
                "project_name": project_name,
                "base_path": base_path,
                "tool_registry": tool_registry,
                "repo_ids": repo_ids,
                "tool_ids": tool_ids,
                "domains": domains,
                "skip_tool_ids": skip_tool_ids,
                "skip_enrichment": skip_enrichment,
                "prompt": prompt,
                "reporter": reporter,
                "event_sink": event_sink,
                "display": display,
                "cancel_token": cancel_token,
                "run_repo": run_repo,
                "chat_session_repo": chat_session_repo,
            },
            name=f"scan-run-{run_id}",
            daemon=True,
        )
        thread.start()
        return ScanHandle(run_id=run_id, result=future)

    def _run_worker(
        self,
        *,
        future: Future[ScanSummary],
        holder_token: str,
        run_id: int,
        project_id: int,
        project_name: str,
        base_path: str,
        tool_registry: ToolRegistry,
        repo_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
        domains: tuple[str, ...],
        skip_tool_ids: tuple[str, ...],
        skip_enrichment: bool,
        prompt: UserPromptPort,
        reporter: ProgressReporter | None,
        event_sink: ScanEventSink | None,
        display: DisplayProtocol | None,
        cancel_token: CancellationToken,
        run_repo: RunRepositoryPort,
        chat_session_repo: ChatSessionRepositoryPort,
    ) -> None:
        # Imports deferred to thread entry to avoid circular-import risk
        # and to keep module import side-effects minimal.
        from application.pipeline.factory import PipelineFactory
        from application.tools.registry import discover_tools

        setup_ok = False
        try:
            # Re-discover tools so the registry reflects this project's
            # per-project overrides.
            discover_tools(tool_registry, base_path, project_name=project_name)

            executor = ToolExecutor(
                project_name=project_name,
                base_path=Path(base_path),
                prompt=prompt,
                subprocess_runner=SubprocessRunner(),
                reporter=reporter,
            )
            pipeline_bus = PipelineFactory.create(
                reporter=reporter,
                skip_enrichment=skip_enrichment,
                project_id=project_id,
                event_sink=event_sink,
                cancel_token=cancel_token,
            )
            orchestrator = ScanOrchestrator(
                project=project_name,
                tool_registry=tool_registry,
                tool_executor=executor,
                event_bus=pipeline_bus,
                prompt=prompt,
                run_id=run_id,
                factory=ToolWrapperFactory(),
                event_sink=event_sink,
                cancel_token=cancel_token,
                run_repository=run_repo,
                project_id=project_id,
                chat_session_repo=chat_session_repo,
                display=display,
            )
            setup_ok = True

            summary = orchestrator.run_scoped_scan(
                repo_names=list(repo_ids) or None,
                tool_names=list(tool_ids) or None,
                domains=list(domains) or None,
                skip_tools=set(skip_tool_ids) or None,
            )
            future.set_result(summary)
        except Exception as exc:
            if not setup_ok:
                # Setup-stage failure (discover_tools, pipeline build,
                # orchestrator construction): the orchestrator never ran
                # so it never persisted or emitted anything. The service
                # is the only path through which the API/REPL can learn,
                # so write the row + emit RunFailed here.
                logger.exception("scan run %d setup failed", run_id)
                _safe_persist_failed(run_repo, run_id)
                _safe_emit_run_failed(event_sink, run_id, project_id, exc)
            else:
                # Body-stage failure: ScanOrchestrator._run already
                # persisted 'cancelled' / 'failed' and emitted the
                # matching SSE event. Propagate via the future.
                logger.exception("scan run %d failed", run_id)
            future.set_exception(exc)
        finally:
            self._scan_run_registry.unregister(run_id)
            try:
                self._lock_registry.release_job(SCAN_LOCK_KIND, holder_token)
            except HolderMismatch:
                logger.warning("lock holder mismatch on scan run %d release", run_id)
            except KeyError:
                logger.warning("scan lock already released for run %d", run_id)


def _resolve_arg_profile_snapshots(
    profiles_repo: ToolArgProfilesRepositoryPort,
    arg_profile_ids: list[int] | None,
) -> dict[str, str]:
    """Validate ids and return ``{tool_name: snapshot_json}``.

    Later ids win on duplicate ``tool_name`` per D-PLAN-2. Raises
    :class:`ValueError` listing missing ids when validation fails.
    """
    if not arg_profile_ids:
        return {}
    existing = set(profiles_repo.existing_ids(arg_profile_ids))
    missing = sorted(set(arg_profile_ids) - existing)
    if missing:
        raise ValueError(f"unknown arg profile ids: {missing}")
    snapshots: dict[str, str] = {}
    for profile_id in arg_profile_ids:
        profile = profiles_repo.get(profile_id)
        if profile is None:
            raise ValueError(f"unknown arg profile ids: [{profile_id}]")
        snapshots[profile.tool_name] = json.dumps([asdict(arg) for arg in profile.args])
    return snapshots


def _safe_persist_failed(run_repo: RunRepositoryPort, run_id: int) -> None:
    try:
        run_repo.set_status(run_id, "failed")
        run_repo.set_finished_at(run_id, _utc_now_iso())
    except Exception:
        logger.exception("failed to persist failure status; suppressing")


def _safe_emit_run_failed(
    event_sink: ScanEventSink | None,
    run_id: int,
    project_id: int,
    exc: BaseException,
) -> None:
    if event_sink is None:
        return
    try:
        event_sink.emit(
            se.RunFailed(
                run_id=run_id,
                project_id=project_id,
                message=f"{type(exc).__name__}: {exc}",
            )
        )
    except Exception:
        logger.exception("failed to emit RunFailed; suppressing")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


_SERVICE: ScanService | None = None


def get_scan_service() -> ScanService:
    """Return the process-shared :class:`ScanService` singleton."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ScanService()
    return _SERVICE
