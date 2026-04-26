"""Background draft runner — spawns the worker thread for draft generation.

Mirrors :mod:`web.reports.runner`. The HTTP POST /reports/drafts endpoint
acquires the ``report`` LockRegistry slot synchronously, then hands
control to :func:`start_draft_thread` which:

1. Wires the EventBus-backed draft event sink and cancellation token.
2. Registers the run in :class:`DraftRunRegistry` so cancel endpoints
   can find the token.
3. Calls :func:`application.reporting.draft_orchestrator.run_draft`.
4. Releases the lock and unregisters the run in ``finally``.

The orchestrator owns all repo state transitions; the runner only
acquires and releases the process-wide lock.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.reporting.draft_orchestrator import (
    DraftCancelled,
    DraftOverwriteDenied,
    DraftRequest,
    run_draft,
)
from infrastructure.events.bus import EventBus
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.drafts import DraftRepository
from web.adapters.draft_run_registry import DraftRunRegistry
from web.adapters.event_bus_draft_sink import EventBusDraftSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter

logger = logging.getLogger("tally.web.reports")


@dataclass(frozen=True)
class WebDraftRequest:
    """Parsed POST body for /api/v1/projects/{id}/reports/drafts."""

    section: str
    force_overwrite: bool


def start_draft_thread(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    request: WebDraftRequest,
    holder_token: str,
    factory: ConnectionFactory,
    bus: EventBus,
    draft_run_registry: DraftRunRegistry,
    lock_registry: LockRegistry | None = None,
) -> threading.Thread:
    """Spawn a daemon worker thread to execute draft generation.

    The caller has ALREADY acquired the LockRegistry "report" slot under
    *holder_token*. The worker takes ownership and releases it in its
    ``finally`` block.
    """
    cancel_token = CancellationToken()
    draft_run_registry.register(
        section=request.section,
        project_id=project_id,
        cancel_token=cancel_token,
    )

    thread = threading.Thread(
        target=_run_draft,
        kwargs={
            "base_path": base_path,
            "project_name": project_name,
            "project_id": project_id,
            "request": request,
            "holder_token": holder_token,
            "factory": factory,
            "bus": bus,
            "cancel_token": cancel_token,
            "lock_registry": lock_registry or get_registry(),
            "draft_run_registry": draft_run_registry,
        },
        name=f"draft-{request.section}",
        daemon=True,
    )
    thread.start()
    return thread


def _run_draft(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    request: WebDraftRequest,
    holder_token: str,
    factory: ConnectionFactory,
    bus: EventBus,
    cancel_token: CancellationToken,
    lock_registry: LockRegistry,
    draft_run_registry: DraftRunRegistry,
) -> None:
    sink = EventBusDraftSink(bus)
    repo = DraftRepository(factory)

    orchestrator_request = DraftRequest(
        project=project_name,
        base_path=Path(base_path),
        section=request.section,
        force_overwrite=request.force_overwrite,
        project_id=project_id,
    )

    try:
        try:
            run_draft(
                orchestrator_request,
                prompt=NoApprovalPromptAdapter(),
                repo=repo,
                event_sink=sink,
                cancel_token=cancel_token,
            )
        except DraftCancelled:
            logger.info("draft run %r cancelled", request.section)
            return
        except DraftOverwriteDenied as exc:
            logger.info("draft run %r overwrite denied: %s", request.section, exc)
            return
        except Exception:  # noqa: BLE001
            logger.exception("draft run %r failed", request.section)
            return
    finally:
        draft_run_registry.unregister(request.section)
        try:
            lock_registry.release_job("report", holder_token)
        except HolderMismatch:
            logger.warning(
                "lock holder mismatch on draft run %r release", request.section
            )
