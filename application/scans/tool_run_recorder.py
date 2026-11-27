"""Records how each tool ended for each repo and service in a scan run."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.pipeline import scan_events as se

if TYPE_CHECKING:
    from collections.abc import Callable

    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.ports.run_repository import RunRepositoryPort
    from domain.pipeline.events import IngestCompleted

logger = logging.getLogger(__name__)

STORAGE_FAILED_REASON = "findings could not be stored"

_RUN_END_REASONS: dict[type, str] = {
    se.RunCompleted: "scan ended before the tool finished",
    se.RunCancelled: "scan cancelled",
    se.RunFailed: "scan failed",
}

type _ToolKey = tuple[str, str, str]


class ToolRunRecorder:
    """Writes one run_tools row per tool, repo and service."""

    def __init__(
        self,
        run_repo: RunRepositoryPort,
        repo_repo: ProjectRepoRepositoryPort,
        *,
        run_id: int,
        domain_of: Callable[[str], str | None],
    ) -> None:
        self._runs = run_repo
        self._repos = repo_repo
        self._run_id = run_id
        self._domain_of = domain_of
        self._row_ids: dict[_ToolKey, int] = {}
        self._running: set[_ToolKey] = set()
        self._repo_ids: dict[str, int | None] = {}

    def emit(self, event: se.ScanEvent) -> None:
        # Scan types call the sink unguarded, so a write failure here
        # must not abort the scan.
        try:
            self._on_scan_event(event)
        except Exception:
            logger.exception("tool run recorder failed on %s", type(event).__name__)

    def on_ingest_completed(self, event: IngestCompleted) -> None:
        try:
            self._on_storage_result(event)
        except Exception:
            logger.exception("tool run recorder failed on IngestCompleted")

    def _on_scan_event(self, event: se.ScanEvent) -> None:
        if isinstance(event, se.ToolStarted):
            self._start(event)
        elif isinstance(event, se.ToolCompleted):
            key = _key(event)
            if key in self._running:
                self._runs.update_tool_run(
                    self._row_ids[key],
                    exit_code=event.exit_code,
                    finished_at=event.timestamp,
                )
        elif isinstance(event, se.ToolFailed):
            self._close(
                _key(event),
                "failed",
                reason=event.message,
                finished_at=event.timestamp,
                exit_code=event.exit_code,
            )
        elif isinstance(event, se.ToolSkipped):
            self._skip(event)
        elif type(event) in _RUN_END_REASONS:
            self._runs.fail_running_tool_runs(
                self._run_id, _RUN_END_REASONS[type(event)]
            )
            self._running.clear()

    def _on_storage_result(self, event: IngestCompleted) -> None:
        key = (event.repo or "", event.service or "", event.tool)
        # A failed tool also gets a storage result; only a row that is
        # still running may be closed by it.
        if key not in self._running:
            return
        row_id = self._row_ids[key]
        if event.stored:
            self._runs.update_tool_run(
                row_id, status="done", findings_count=len(event.ids)
            )
        else:
            self._runs.update_tool_run(
                row_id, status="failed", reason=STORAGE_FAILED_REASON
            )
        self._running.discard(key)

    def _start(self, event: se.ToolStarted) -> None:
        key = _key(event)
        row_id = self._row_ids.pop(key, None)
        if row_id is not None:
            # update_tool_run ignores None, so a reused row would keep the
            # previous attempt's reason, exit code and finish time.
            self._runs.delete_tool_run(row_id)
            self._running.discard(key)
        self._insert(key, status="running", started_at=event.timestamp)

    def _skip(self, event: se.ToolSkipped) -> None:
        key = _key(event)
        if event.kind == se.SKIP_NOT_APPLICABLE:
            row_id = self._row_ids.pop(key, None)
            self._running.discard(key)
            if row_id is not None:
                self._runs.delete_tool_run(row_id)
            return
        status = "skipped" if event.kind == se.SKIP_DECLINED else "failed"
        self._close(key, status, reason=event.skip_reason, finished_at=event.timestamp)

    def _close(
        self,
        key: _ToolKey,
        status: str,
        *,
        reason: str,
        finished_at: str,
        exit_code: int | None = None,
    ) -> None:
        row_id = self._row_ids.get(key)
        if row_id is None:
            row_id = self._insert(
                key, status=status, finished_at=finished_at, reason=reason
            )
            if row_id is not None and exit_code is not None:
                self._runs.update_tool_run(row_id, exit_code=exit_code)
            return
        if exit_code is None:
            self._runs.update_tool_run(
                row_id, status=status, reason=reason, finished_at=finished_at
            )
        else:
            self._runs.update_tool_run(
                row_id,
                status=status,
                reason=reason,
                finished_at=finished_at,
                exit_code=exit_code,
            )
        self._running.discard(key)

    def _insert(
        self,
        key: _ToolKey,
        *,
        status: str,
        started_at: str | None = None,
        finished_at: str | None = None,
        reason: str | None = None,
    ) -> int | None:
        repo_name, service, tool = key
        repo_id: int | None = None
        if repo_name:
            repo_id = self._repo_id(repo_name)
            if repo_id is None:
                # A null repo means "no repo applies"; an unknown name is
                # an error and must not be stored as one.
                logger.error("no active repository named %r; row skipped", repo_name)
                return None
        row_id = self._runs.add_tool_run(
            run_id=self._run_id,
            tool=tool,
            repo_id=repo_id,
            service=service or None,
            domain=self._domain_of(tool),
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            reason=reason,
        )
        self._row_ids[key] = row_id
        if status == "running":
            self._running.add(key)
        return row_id

    def _repo_id(self, repo_name: str) -> int | None:
        if repo_name not in self._repo_ids:
            self._repo_ids[repo_name] = self._repos.find_id_by_name(repo_name)
        return self._repo_ids[repo_name]


def _key(
    event: se.ToolStarted | se.ToolCompleted | se.ToolFailed | se.ToolSkipped,
) -> _ToolKey:
    return (event.repo, event.service, event.tool)
