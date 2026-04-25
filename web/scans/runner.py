"""Background scan runner — spawns the ``threading.Thread`` that owns a scan.

The HTTP start endpoint validates inputs, acquires the ``LockRegistry``
job slot synchronously (so 409 returns immediately), creates the
``scan_runs`` row, then hands control to ``start_scan_thread`` which:

1. Constructs a fresh ``ScanOrchestrator`` for the worker thread —
   ``ToolRegistry`` is re-discovered inside the thread because the
   registry is process-global state and other workers may have mutated
   it.
2. Wires the EventBus-backed event sink, the no-approval prompt
   adapter, and the cancellation token.
3. Registers the run in ``ScanRunRegistry`` so cancel endpoints can
   find it.
4. Dispatches the right ``run_*`` method based on request shape.
5. Releases the lock and unregisters the run in ``finally``.

If the orchestrator emits ``run_failed`` / ``run_cancelled`` it has
already persisted the matching ``scan_runs.status`` — the runner only
swallows the exception so the worker thread exits cleanly.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.tools.executor import ToolExecutor
from application.tools.orchestrator import ScanCancelled, ScanOrchestrator
from domain.tools.scan_types import SEGMENT_ORDER
from infrastructure.events.bus import EventBus
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository
from web.adapters.event_bus_scan_sink import EventBusScanSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
from web.adapters.scan_run_registry import ScanRunRegistry

logger = logging.getLogger("tally.web.scans")


@dataclass(frozen=True)
class ScanRequest:
    """Parsed request body for POST /api/v1/projects/{id}/scans."""

    repo_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    domains: tuple[str, ...]
    skip_tool_ids: tuple[str, ...]
    skip_enrichment: bool


def start_scan_thread(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    run_id: int,
    request: ScanRequest,
    holder_token: str,
    factory: ConnectionFactory,
    bus: EventBus,
    lock_registry: LockRegistry | None = None,
    scan_run_registry: ScanRunRegistry,
) -> threading.Thread:
    """Spawn a daemon worker thread to execute the scan.

    The caller has ALREADY acquired the LockRegistry "scan" slot under
    *holder_token*. The worker takes ownership and releases it in its
    finally block.
    """
    cancel_token = CancellationToken()
    scan_run_registry.register(
        run_id=run_id,
        project_id=project_id,
        cancel_token=cancel_token,
    )

    thread = threading.Thread(
        target=_run_scan,
        kwargs={
            "base_path": base_path,
            "project_name": project_name,
            "project_id": project_id,
            "run_id": run_id,
            "request": request,
            "holder_token": holder_token,
            "factory": factory,
            "bus": bus,
            "cancel_token": cancel_token,
            "lock_registry": lock_registry or get_registry(),
            "scan_run_registry": scan_run_registry,
        },
        name=f"scan-run-{run_id}",
        daemon=True,
    )
    thread.start()
    return thread


def _run_scan(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    run_id: int,
    request: ScanRequest,
    holder_token: str,
    factory: ConnectionFactory,
    bus: EventBus,
    cancel_token: CancellationToken,
    lock_registry: LockRegistry,
    scan_run_registry: ScanRunRegistry,
) -> None:
    try:
        from application.pipeline.factory import PipelineFactory
        from application.tools.factory import ToolWrapperFactory
        from application.tools.registry import discover_tools, tool_registry

        # Re-discover tools so the registry reflects this project's overrides.
        discover_tools(base_path, project_name=project_name)

        prompt = NoApprovalPromptAdapter()
        executor = ToolExecutor(
            project_name=project_name,
            base_path=Path(base_path),
            prompt=prompt,
        )
        pipeline_bus = PipelineFactory.create(
            console=None,
            skip_enrichment=request.skip_enrichment,
        )
        run_repo = RunRepository(factory)
        sink = EventBusScanSink(bus)

        orchestrator = ScanOrchestrator(
            project=project_name,
            tool_registry=tool_registry,
            tool_executor=executor,
            event_bus=pipeline_bus,
            prompt=prompt,
            run_id=run_id,
            factory=ToolWrapperFactory(),
            console=None,
            lock_registry=lock_registry,
            event_sink=sink,
            cancel_token=cancel_token,
            run_repository=run_repo,
            project_id=project_id,
        )

        try:
            _dispatch(orchestrator, request)
        except ScanCancelled:
            logger.info("scan run %d cancelled", run_id)
        except Exception:  # noqa: BLE001
            logger.exception("scan run %d failed", run_id)
    finally:
        scan_run_registry.unregister(run_id)
        try:
            lock_registry.release_job("scan", holder_token)
        except HolderMismatch:
            logger.warning("lock holder mismatch on scan run %d release", run_id)


def _dispatch(orchestrator: ScanOrchestrator, request: ScanRequest) -> None:
    """Pick the right run_*() method based on the parsed request shape."""
    repos = list(request.repo_ids)
    tools = list(request.tool_ids)
    domains = list(request.domains)
    excluded_segments = (
        [s for s in SEGMENT_ORDER if s not in domains] if domains else []
    )
    excluded_tools = set(request.skip_tool_ids)

    # Single tool on a single repo
    if len(tools) == 1 and len(repos) == 1:
        orchestrator.run_tool_on_repo(tools[0], repos[0])
        return

    # Single tool across all repos
    if len(tools) == 1 and not repos:
        orchestrator.run_tool_on_all_repos(tools[0])
        return

    # Single repo (multi-tool) — exclude_tools applies
    if len(repos) == 1 and not tools:
        orchestrator.run_repo_scan(repos[0], exclude_tools=excluded_tools)
        return

    # Single segment across all repos and tools
    if len(domains) == 1 and not repos and not tools:
        orchestrator.run_segment(domains[0])
        return

    # General case: full scan with segment / tool exclusions
    orchestrator.run_full_scan(
        exclude_segments=excluded_segments,
        exclude_tools=excluded_tools,
    )
