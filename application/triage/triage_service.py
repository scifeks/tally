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
from typing import TYPE_CHECKING, Any, Literal

from application.anthropic.mode_availability import (
    BackgroundModeAvailability,
    BackgroundModeAvailabilityService,
)
from application.events.ids import new_event_id
from application.events.types import BusEvent
from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.sync.integration_sync import run_configured_syncs
from application.triage.factory import (
    ResolvedTriageConfig,
    ensure_triage_backend_configured,
    resolve_triage_config,
)
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

_RESUMABLE_STATUSES = ("failed", "running", "rate_limited")


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


class TriageConfigurationError(ValueError):
    """Raised for invalid triage configuration combinations."""


class TriageCredentialsError(ValueError):
    """Raised when background-mode credentials are missing or invalid."""


@dataclass(frozen=True)
class ResolvedBilling:
    """Billing resolution result with auto-failover signal.

    ``auto_failover_permitted`` is True only when neither an explicit arg
    nor a config default was present, so callers can distinguish
    "defaulted to plan" from "explicitly chose plan".
    """

    method: Literal["plan", "api"]
    auto_failover_permitted: bool


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
        interaction_mode: Literal["interactive", "background"] | None = None,
        billing_method: Literal["plan", "api"] | None = None,
        api_key: str | None = None,
    ) -> TriageStartHandle:
        """Start a triage run against the latest scan_run for a project.

        When ``interaction_mode`` is ``"interactive"``, dispatches via the
        existing Docker/MCP code path; ``billing_method`` and ``api_key``
        must be None.

        When ``interaction_mode`` is ``"background"``, validates credentials
        and routes to the ``claude_sdk`` adapter.  Billing is resolved from
        the explicit arg, then ``claude.default_billing_method`` in config,
        then defaults to ``"plan"``.  The resolved provider override and
        billing flow through to the runner and factory.

        When ``interaction_mode`` is None (legacy callers), uses the
        config-driven provider without mode-specific validation.
        ``billing_method`` must also be None in this case.

        Raises NoScanRunError if no scan_runs exist, JobBusy if another
        triage holds the lock, TriageConfigurationError for invalid
        mode/billing combinations, ValueError for missing credentials.
        """
        del finding_ids  # finding-scoped triage is reserved for later

        if interaction_mode is None and billing_method is not None:
            raise TriageConfigurationError(
                "billing_method requires interaction_mode='background'"
            )

        if interaction_mode == "interactive" and billing_method is not None:
            raise TriageConfigurationError(
                "billing_method must be None for interactive mode."
            )

        resolved_config: ResolvedTriageConfig | None = None

        if interaction_mode == "background":
            resolved_config = self._resolve_background_config(
                base_path, billing_method, api_key
            )
            logger.info(
                "background triage: provider=claude_sdk billing=%s auto_failover=%s",
                resolved_config.billing_method,
                resolved_config.auto_failover,
            )
        else:
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
            resolved_config=resolved_config,
        )

    def _resolve_background_config(
        self,
        base_path: str,
        billing_method: Literal["plan", "api"] | None,
        api_key: str | None,
    ) -> ResolvedTriageConfig:
        """Build a ResolvedTriageConfig for background mode.

        Shared by ``start_triage`` and ``resume_triage``.
        """
        cfg = ConfigManager(base_path).global_config
        availability = BackgroundModeAvailabilityService(cfg).evaluate()
        resolved_billing = self._resolve_billing_method(cfg, billing_method)
        self._validate_background_credentials(resolved_billing.method, availability)
        api_key_source = api_key or (cfg.claude.api_key if cfg.claude else None)
        base_resolved = resolve_triage_config(app_root=Path(base_path))
        return ResolvedTriageConfig(
            provider_name="claude_sdk",
            base_url=base_resolved.base_url,
            model=base_resolved.model,
            timeout_seconds=base_resolved.timeout_seconds,
            retry_count=base_resolved.retry_count,
            debug=base_resolved.debug,
            billing_method=resolved_billing.method,
            api_key_source=api_key_source,
            auto_failover=resolved_billing.auto_failover_permitted,
        )

    @staticmethod
    def _resolve_billing_method(
        cfg: Any,
        explicit: Literal["plan", "api"] | None,
    ) -> ResolvedBilling:
        """Resolve the billing method for background triage.

        Priority: explicit arg > config default > fallback to "plan".
        Auto-failover is only permitted when both the explicit arg and
        the config default were absent.
        """
        if explicit is not None:
            return ResolvedBilling(method=explicit, auto_failover_permitted=False)
        default = cfg.claude.default_billing_method if cfg.claude else None
        if default is not None:
            return ResolvedBilling(
                method=default.lower(), auto_failover_permitted=False
            )
        return ResolvedBilling(method="plan", auto_failover_permitted=True)

    @staticmethod
    def _validate_background_credentials(
        billing: Literal["plan", "api"],
        availability: BackgroundModeAvailability,
    ) -> None:
        if billing == "plan" and not availability.oauth_available:
            raise TriageCredentialsError(
                "Cannot start plan-billed background triage: "
                f"{availability.oauth_reason}"
            )
        if billing == "api" and not availability.api_key_available:
            raise TriageCredentialsError(
                "Cannot start api-billed background triage: "
                f"{availability.api_key_reason}"
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
        interaction_mode: Literal["interactive", "background"] | None = None,
        billing_method: Literal["plan", "api"] | None = None,
        api_key: str | None = None,
    ) -> TriageStartHandle:
        """Resume an existing triage run for a project.

        Accepts the same ``interaction_mode`` / ``billing_method`` /
        ``api_key`` parameters as ``start_triage`` so callers can switch
        billing pool on resume (e.g. plan -> api after a rate limit).

        Raises TriageNotResumableError if the run does not exist or is in
        a terminal state, JobBusy if another triage holds the lock.
        """
        if interaction_mode is None and billing_method is not None:
            raise TriageConfigurationError(
                "billing_method requires interaction_mode='background'"
            )

        if interaction_mode == "interactive" and billing_method is not None:
            raise TriageConfigurationError(
                "billing_method must be None for interactive mode."
            )

        resolved_config: ResolvedTriageConfig | None = None

        if interaction_mode == "background":
            resolved_config = self._resolve_background_config(
                base_path, billing_method, api_key
            )
            logger.info(
                "background resume: provider=claude_sdk billing=%s",
                resolved_config.billing_method,
            )
        else:
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
            resolved_config=resolved_config,
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
        resolved_config: ResolvedTriageConfig | None = None,
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
                "resolved_config": resolved_config,
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
        resolved_config: ResolvedTriageConfig | None = None,
    ) -> None:
        sink = event_sink
        uses_sdk = (
            resolved_config is not None
            and resolved_config.provider_name == "claude_sdk"
        )
        try:
            try:
                from application.agent_sandbox.container import ensure_containers
                from application.agent_sandbox.image import ensure_image
                from application.triage.factory import resolve_triage_config

                resolved = resolved_config or resolve_triage_config(
                    app_root=Path(base_path)
                )
                ensure_image(Path(base_path))
                ensure_containers(
                    Path(base_path),
                    provider=resolved.provider_name,
                    base_url=resolved.base_url,
                    model=resolved.model,
                    repo_paths=self._repo_paths,
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
                        resolved_config=resolved_config,
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
                        resolved_config=resolved_config,
                    )
                future.set_result(result)
                if result.get("status") == "rate_limited":
                    logger.info(
                        "triage scan_run_id=%d ended with rate_limited; "
                        "skipping post-triage sync",
                        scan_run_id,
                    )
                else:
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
            if not uses_sdk:
                try:
                    from application.agent_sandbox.container import (
                        teardown_containers,
                    )

                    teardown_containers(Path(base_path))
                except Exception:
                    logger.debug(
                        "post-triage container teardown failed",
                        exc_info=True,
                    )

    # Snapshot queries

    async def build_snapshot_event(
        self,
        project_id: int,
        scan_run_id: int,
        *,
        after_batch_id: int | None = None,
    ) -> BusEvent:
        """Build the on-connect snapshot for a run-scoped triage SSE stream."""
        payload: dict[str, Any] = {
            "project_id": project_id,
            "scan_run_id": scan_run_id,
            "after_batch_id": after_batch_id,
        }
        summary = await asyncio.to_thread(
            self._triage_repo.summarize_for_run,
            scan_run_id,
            after_batch_id=after_batch_id,
        )
        if summary is not None:
            batches = await asyncio.to_thread(
                self._triage_repo.list_for_run,
                scan_run_id,
                include_cancelled=True,
                after_batch_id=after_batch_id,
            )
            payload.update(
                status=summary.status,
                total_findings=summary.total_findings,
                processed_findings=summary.processed_findings,
                started_at=summary.started_at,
                finished_at=summary.finished_at,
                batches=[self._batch_to_dict(b) for b in batches],
            )

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
