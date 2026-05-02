"""Background draft runner.

The HTTP draft route acquires the ``report`` LockRegistry slot
synchronously, then hands the lock off to a daemon worker spawned
here. The worker takes ownership of the slot and releases it in its
``finally`` block. The orchestrator owns all repo state transitions;
the runner only manages the process-wide lock.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
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
from infrastructure.events.bus import EventBus
from web.adapters.draft_run_registry import DraftRunRegistry
from web.adapters.event_bus_draft_sink import EventBusDraftSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter

if TYPE_CHECKING:
    from application.ports.draft_repository import DraftRepositoryPort

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
    draft_repo: DraftRepositoryPort,
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
            "draft_repo": draft_repo,
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
    draft_repo: DraftRepositoryPort,
    bus: EventBus,
    cancel_token: CancellationToken,
    lock_registry: LockRegistry,
    draft_run_registry: DraftRunRegistry,
) -> None:
    sink = EventBusDraftSink(bus)

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
                repo=draft_repo,
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
        except KeyError:
            logger.warning(
                "report lock already released for draft run %r", request.section
            )
