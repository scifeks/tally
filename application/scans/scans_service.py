"""Application service for the scan_runs persistence surface.

Owns per-request construction of the run repository so route modules
do not import infrastructure persistence directly. Also owns the
startup-time stale-scan sweep so the web composition root drops its
``ConnectionFactory`` / ``RunRepository`` / ``ProjectPaths`` imports.
Owns the cancel orchestration (``cancel_scan``, ``cancel_all``) and
the SSE on-connect snapshot accessors (``peek_active_run``,
``list_active_runs``) so route bodies stop poking the
``ScanRunRegistry`` directly.
Owns scan-start validation rules so route adapters do not contain
business logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from application.tools.scan_run_registry import (
    ScanRunHandle,
    ScanRunRegistry,
    get_scan_run_registry,
)
from core.project_paths import ProjectPaths
from domain.scans.entry import SCAN_RUN_STATUSES
from domain.tools.scan_types import SEGMENT_ORDER
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository

if TYPE_CHECKING:
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.tool_arg_profiles import ToolArgProfilesRepositoryPort
    from application.project.registry_service import ProjectRegistryService
    from application.project.repositories_service import ProjectRepositoriesService
    from application.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldError:
    """Single field validation failure."""

    field: str
    issue: str


class ScanValidationError(Exception):
    """Raised when one or more scan request validation rules fail."""

    def __init__(self, fields: list[FieldError]) -> None:
        self.fields: tuple[FieldError, ...] = tuple(fields)
        super().__init__(f"validation failed: {len(self.fields)} field error(s)")


@dataclass(frozen=True)
class StartScanResolved:
    """Values derived during validation that the route needs for dispatch."""

    repo_names: list[str]


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class ScanNotFound(LookupError):
    """Raised when a run_id is unknown to the registry and the run repo,
    or when a persisted row's project_id does not match the bound project.
    """


class ScanNotCancellable(Exception):
    """Raised when a scan_runs row exists but is not in a live state.

    Carries the persisted status string so the route can surface it to
    the client.
    """

    def __init__(self, status: str) -> None:
        super().__init__(f"scan run is not cancellable (status={status!r})")
        self.status = status


class ScansService:
    """Scan_runs facade bound to a single project."""

    def __init__(
        self,
        run_repo: RunRepositoryPort,
        *,
        project_id: int,
        scan_run_registry: ScanRunRegistry | None = None,
    ) -> None:
        self._run_repo = run_repo
        self._project_id = project_id
        self._registry = scan_run_registry or get_scan_run_registry()

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
        return cls(run_repo=RunRepository(factory), project_id=project_id)

    @property
    def run_repo(self) -> RunRepositoryPort:
        return self._run_repo

    @property
    def project_id(self) -> int:
        return self._project_id

    def record_run_tool_counts(
        self, run_id: int, findings_by_tool: dict[str, int]
    ) -> None:
        """Persist aggregate per-tool finding counts for a completed run.

        No-op when ``findings_by_tool`` is empty. Translates the
        domain-shaped mapping into the row shape
        ``RunRepositoryPort.add_run_tools`` accepts.
        """
        if not findings_by_tool:
            return
        rows = [
            {"tool": tool, "findings_count": count}
            for tool, count in findings_by_tool.items()
        ]
        self._run_repo.add_run_tools(run_id, rows)

    def cancel_scan(self, run_id: int) -> None:
        """Signal cancellation for a single scan run owned by this project.

        Looks up the live handle in the run registry; if absent, falls
        back to the run repo to distinguish unknown from finished. On
        a live handle, sets the cancel token and writes the DB status
        to ``cancelling``. Mirrors ``ChatSessionService.cancel_stream``.

        Raises:
            ScanNotFound: run id unknown, or row belongs to a different
                project.
            ScanNotCancellable: row exists but is not in a live state.
        """
        handle = self._registry.get(run_id)
        if handle is None:
            row = self._run_repo.get(run_id)
            if row is None or row.project_id != self._project_id:
                raise ScanNotFound(f"scan run {run_id} not found")
            raise ScanNotCancellable(row.status or "unknown")

        if handle.project_id != self._project_id:
            raise ScanNotFound(f"scan run {run_id} not found")

        handle.cancel_token.set()
        self._safe_mark_cancelling(run_id)

    def cancel_all(self) -> list[int]:
        """Cancel every active scan for this project.

        Sets each cancel token, then writes ``cancelling`` to the DB.
        Per-row DB write failures are logged and swallowed. Returns the
        run ids that received the cancel signal.
        """
        cancelled: list[int] = []
        for handle in self._registry.list_for_project(self._project_id):
            handle.cancel_token.set()
            cancelled.append(handle.run_id)
        for run_id in cancelled:
            self._safe_mark_cancelling(run_id)
        return cancelled

    def peek_active_run(self, run_id: int) -> ScanRunHandle | None:
        """Registry handle for a live run, or None.

        Used by the SSE on-connect snapshot to project the
        ``current_repo`` / ``current_tool`` fields without forcing the
        route to know the registry shape.
        """
        return self._registry.get(run_id)

    def list_active_runs(self) -> list[ScanRunHandle]:
        """Live scan handles for this project."""
        return self._registry.list_for_project(self._project_id)

    def validate_start_request(
        self,
        *,
        repo_ids: list[int],
        tool_ids: list[str],
        skip_tool_ids: list[str],
        domains: list[str],
        arg_profile_ids: list[int],
        repos_service: ProjectRepositoriesService,
        tool_registry: ToolRegistry,
        profiles_repo: ToolArgProfilesRepositoryPort,
    ) -> StartScanResolved:
        """Validate a start-scan request and return resolved values.

        Aggregates all field errors before raising so the caller sees
        every problem at once.
        """
        errors: list[FieldError] = []

        lookup = repos_service.find_by_ids(self._project_id, repo_ids)
        if lookup.missing:
            errors.append(
                FieldError(field="repoIds", issue=f"unknown repo ids: {lookup.missing}")
            )

        valid_tools = {tw.name for tw in tool_registry.get_all_tools()}
        bad_tool_ids = [t for t in tool_ids if t not in valid_tools]
        if bad_tool_ids:
            errors.append(
                FieldError(field="toolIds", issue=f"unknown tool names: {bad_tool_ids}")
            )
        bad_skip_ids = [t for t in skip_tool_ids if t not in valid_tools]
        if bad_skip_ids:
            errors.append(
                FieldError(
                    field="skipToolIds", issue=f"unknown tool names: {bad_skip_ids}"
                )
            )

        valid_domains = set(SEGMENT_ORDER)
        bad_domains = [d for d in domains if d not in valid_domains]
        if bad_domains:
            errors.append(
                FieldError(field="domains", issue=f"unknown domains: {bad_domains}")
            )

        if arg_profile_ids:
            existing = set(profiles_repo.existing_ids(arg_profile_ids))
            for idx, pid in enumerate(arg_profile_ids):
                if pid not in existing:
                    errors.append(
                        FieldError(
                            field=f"argProfileIds[{idx}]",
                            issue=f"unknown profile id {pid}",
                        )
                    )

        if errors:
            raise ScanValidationError(errors)

        repo_names = [lookup.found[rid].name for rid in repo_ids]
        return StartScanResolved(repo_names=repo_names)

    def validate_status(self, status: str | None) -> None:
        """Raise ScanValidationError if status is not a known scan status."""
        if status is None:
            return
        if status not in SCAN_RUN_STATUSES:
            raise ScanValidationError(
                [FieldError(field="status", issue=f"unknown scan status {status!r}")]
            )

    def _safe_mark_cancelling(self, run_id: int) -> None:
        try:
            self._run_repo.set_status(run_id, "cancelling")
        except Exception:
            logger.exception("failed to mark scan %d cancelling", run_id)

    @classmethod
    def mark_stale_failed_for_all_projects(
        cls, project_registry: ProjectRegistryService
    ) -> None:
        """Mark every ``running``/``cancelling`` scan_runs row as ``failed``.

        Tier-1 lock guarantees only one scan is live per process at a
        time, so any persisted-as-running row at boot belongs to a prior
        process that is no longer here. Iterates every active project's
        findings DB and sweeps once. Errors per-project are logged and
        skipped so one bad project does not block startup.
        """
        for project in project_registry.list_active():
            try:
                paths = ProjectPaths.from_registry_row(project)
                if not paths.findings_db.exists():
                    continue
                repo = RunRepository(ConnectionFactory(paths.findings_db))
                count = repo.mark_stale_runs_failed()
                if count:
                    logger.info(
                        "marked %d stale scan_runs as failed in project %s",
                        count,
                        project.name,
                    )
            except Exception:
                logger.exception(
                    "stale-scan cleanup failed for project %s", project.name
                )
