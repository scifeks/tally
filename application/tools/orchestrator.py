"""Scan orchestration: coordinate multi-tool scans across segments and repos."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.locking import LockRegistry, get_registry
from application.locking.cancellation import CancellationToken, no_op_token
from application.ports.scan_event_sink import NullScanEventSink, ScanEventSink
from application.ports.user_prompt import UserPromptPort
from application.tools.display import OrchestratorDisplay
from application.tools.executor import ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.registry import ToolRegistry
from application.tools.scan_types import (
    ExecutionResources,
    FullScan,
    RepoScan,
    SegmentScan,
    ToolOnAllReposScan,
    ToolOnRepoScan,
)
from domain.pipeline import scan_events as se
from domain.pipeline.events import EventBus
from domain.tools.scan_types import SEGMENT_ORDER, ScanSummary, ScanTypeConfig

if TYPE_CHECKING:
    from rich.console import Console

    from infrastructure.store.repositories.runs import RunRepository

logger = logging.getLogger(__name__)

__all__ = [
    "ScanSummary",
    "ScanOrchestrator",
    "ScanCancelled",
    "SEGMENT_ORDER",
]


class ScanCancelled(Exception):
    """Raised when a scan observes its CancellationToken set."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ScanOrchestrator:
    """Coordinate multi-tool scans across segments and repositories.

    Args:
        project:        Active project name.
        tool_registry:  Registry of available tool wrappers.
        tool_executor:  Configured executor (carries base_path and project_name).
        event_bus:      Internal pipeline EventBus for ToolCompleted dispatch.
        prompt:         UserPromptPort adapter (REPL or API).
        run_id:         Optional scan_runs.id; required for persistence + lock.
        factory:        Optional ToolWrapperFactory; defaults to a fresh one.
        console:        Optional Rich console for REPL display output.
        lock_registry:  Optional LockRegistry; defaults to the process singleton.
        event_sink:     Optional ScanEventSink for SSE event emission.
                        Defaults to a no-op sink (REPL behavior unchanged).
        cancel_token:   Optional cooperative cancellation flag.
                        Defaults to a process-shared token that is never set.
        run_repository: Optional ``RunRepository`` for persisting status,
                        timestamps, and findings_count. None disables
                        persistence (REPL legacy path).
        project_id:     Optional ``scan_runs.project_id`` carried into event
                        payloads. None for the REPL path.
    """

    def __init__(
        self,
        project: str,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        event_bus: EventBus,
        prompt: UserPromptPort,
        run_id: int | None = None,
        factory: ToolWrapperFactory | None = None,
        console: Console | None = None,
        lock_registry: LockRegistry | None = None,
        event_sink: ScanEventSink | None = None,
        cancel_token: CancellationToken | None = None,
        run_repository: RunRepository | None = None,
        project_id: int | None = None,
    ) -> None:
        self.project_name = project
        self.registry = tool_registry
        self.executor = tool_executor
        self._event_bus = event_bus
        self._prompt = prompt
        self._run_id = run_id
        self.display = OrchestratorDisplay(console=console)
        self._factory = factory or ToolWrapperFactory()
        self._lock_registry = (
            lock_registry if lock_registry is not None else get_registry()
        )
        self._event_sink: ScanEventSink = event_sink or NullScanEventSink()
        self._cancel_token: CancellationToken = cancel_token or no_op_token()
        self._run_repository = run_repository
        self._project_id = project_id

        # Plumb cancellation into the executor so subprocess waits abort.
        if hasattr(tool_executor, "set_cancel_token"):
            tool_executor.set_cancel_token(self._cancel_token)

        from core.config.manager import ConfigManager

        self._config = ConfigManager(str(tool_executor.base_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_config(self, remaining_peers: int = 0) -> ScanTypeConfig:
        return ScanTypeConfig(
            project_name=self.project_name,
            base_path=str(self.executor.base_path),
            config_manager=self._config,
            run_id=self._run_id,
            prompt=self._prompt,
            remaining_peers=remaining_peers,
        )

    def _make_resources(self) -> ExecutionResources:
        return ExecutionResources(
            executor=self.executor,
            registry=self.registry,
            factory=self._factory,
            event_bus=self._event_bus,
            display=self.display,
        )

    def _scan_lock(self) -> AbstractContextManager[None]:
        if self._run_id is None:
            return nullcontext()
        holder = f"scan-run:{self._run_id}"
        return self._lock_registry.job("scan", holder)

    def _emit(self, event: Any) -> None:
        try:
            self._event_sink.emit(event)
        except Exception:
            logger.exception("scan event sink raised; suppressing")

    def _check_cancel(self) -> None:
        if self._cancel_token.is_set():
            raise ScanCancelled

    def _persist(self, fn: Callable[[RunRepository, int], None]) -> None:
        if self._run_repository is None or self._run_id is None:
            return
        try:
            fn(self._run_repository, self._run_id)
        except Exception:
            logger.exception("failed to persist scan_runs update; suppressing")

    # ------------------------------------------------------------------
    # Run orchestration shell
    # ------------------------------------------------------------------

    def _run(self, body: Callable[[], ScanSummary]) -> ScanSummary:
        """Wrap a scan invocation with lock + persistence + event emission.

        Persistence + events are best-effort and never mask the underlying
        scan result. Cancellation surfaces a ``ScanCancelled`` exception.
        """
        run_id = self._run_id or 0
        project_id = self._project_id
        with self._scan_lock():
            self._check_cancel()
            self._persist(lambda r, rid: r.set_status(rid, "running"))
            self._persist(lambda r, rid: r.set_started_at(rid, _utc_now_iso()))
            self._emit(
                se.RunStarted(
                    run_id=run_id,
                    project_id=project_id,
                    message="scan started",
                )
            )
            try:
                summary = body()
            except ScanCancelled:
                self._persist(lambda r, rid: r.set_status(rid, "cancelled"))
                self._persist(lambda r, rid: r.set_finished_at(rid, _utc_now_iso()))
                self._emit(
                    se.RunCancelled(
                        run_id=run_id,
                        project_id=project_id,
                        message="scan cancelled",
                    )
                )
                raise
            except Exception as exc:
                self._persist(lambda r, rid: r.set_status(rid, "failed"))
                self._persist(lambda r, rid: r.set_finished_at(rid, _utc_now_iso()))
                self._emit(
                    se.RunFailed(
                        run_id=run_id,
                        project_id=project_id,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
                raise
            self._persist(
                lambda r, rid: r.set_findings_count(
                    rid, _summary_findings_count(summary)
                )
            )
            self._persist(lambda r, rid: r.set_status(rid, "done"))
            self._persist(lambda r, rid: r.set_finished_at(rid, _utc_now_iso()))
            self._emit(
                se.RunCompleted(
                    run_id=run_id,
                    project_id=project_id,
                    message="scan complete",
                    findings_count=_summary_findings_count(summary),
                )
            )
            return summary

    # ------------------------------------------------------------------
    # Public API — adapter shims
    # ------------------------------------------------------------------

    def run_full_scan(
        self,
        exclude_segments: list[str] | None = None,
        exclude_tools: set[str] | None = None,
    ) -> ScanSummary:
        return self._run(
            lambda: FullScan(exclude_segments or [], exclude_tools or set()).execute(
                self._make_config(), self._make_resources()
            )
        )

    def run_segment(
        self,
        segment_name: str,
        remaining_peers: int = 0,
    ) -> ScanSummary:
        return self._run(
            lambda: SegmentScan(segment_name).execute(
                self._make_config(remaining_peers=remaining_peers),
                self._make_resources(),
            )
        )

    def run_repo_scan(
        self,
        repo_name: str,
        exclude_dirs: list[str] | None = None,
        severity_filter: str | None = None,
        exclude_tools: set[str] | None = None,
    ) -> ScanSummary:
        del exclude_dirs, severity_filter  # forwarded by callers, unused here
        return self._run(
            lambda: RepoScan(repo_name, exclude_tools or set()).execute(
                self._make_config(), self._make_resources()
            )
        )

    def run_tool_on_all_repos(
        self,
        tool_name: str,
        remaining_peers: int = 0,
    ) -> ScanSummary:
        return self._run(
            lambda: ToolOnAllReposScan(tool_name).execute(
                self._make_config(remaining_peers=remaining_peers),
                self._make_resources(),
            )
        )

    def run_tool_on_repo(
        self,
        tool_name: str,
        repo_name: str,
        remaining_peers: int = 0,
    ) -> ScanSummary:
        return self._run(
            lambda: ToolOnRepoScan(tool_name, repo_name).execute(
                self._make_config(remaining_peers=remaining_peers),
                self._make_resources(),
            )
        )


def _summary_findings_count(summary: ScanSummary) -> int:
    """Best-effort total findings extracted from a ScanSummary."""
    for attr in ("ingested_total", "total_findings", "findings_count"):
        val = getattr(summary, attr, None)
        if isinstance(val, int):
            return val
    rows = getattr(summary, "rows", None)
    if rows is not None:
        try:
            return sum(int(getattr(r, "finding_count", 0) or 0) for r in rows)
        except Exception:
            return 0
    return 0
