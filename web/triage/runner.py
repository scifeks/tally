"""Background triage runner that spawns the worker thread.

Mirrors web.scans.runner. The HTTP start endpoint validates inputs,
acquires the LockRegistry job slot, resolves the latest scan_run_id,
then spawns a worker thread that wires the event sink, registers the run,
calls the triage orchestrator, and releases the lock in its finally block.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import HolderMismatch, LockRegistry, get_registry
from application.locking.cancellation import CancellationToken
from application.triage.orchestrator import (
    resume_triage_for_project,
    run_triage_for_project,
)
from application.triage.runner import NoScanRunError, TriageCancelled
from infrastructure.events.bus import EventBus
from web.adapters.event_bus_triage_sink import EventBusTriageSink
from web.adapters.triage_run_registry import TriageRunRegistry

if TYPE_CHECKING:
    from application.tools.registry import ToolRegistry

logger = logging.getLogger("tally.web.triage")


@dataclass(frozen=True)
class TriageRequest:
    """Parsed request body for POST /api/v1/projects/{id}/triage.

    ``finding_ids`` is reserved for finding-scoped triage; today the
    runner queues all untriaged findings for the latest scan_run.
    """

    finding_ids: tuple[int, ...] | None = None


def start_triage_thread(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    scan_run_id: int,
    request: TriageRequest,
    holder_token: str,
    bus: EventBus,
    tool_registry: ToolRegistry,
    triage_run_registry: TriageRunRegistry,
    lock_registry: LockRegistry | None = None,
    is_resume: bool = False,
) -> threading.Thread:
    """Spawn a daemon worker thread to execute triage.

    The caller has ALREADY acquired the LockRegistry "triage" slot
    under *holder_token*. The worker takes ownership and releases it
    in its ``finally`` block. When ``is_resume`` is True the worker
    calls :func:`resume_triage_for_project` (explicit scan_run_id +
    ``reset_for_resume``); otherwise it calls
    :func:`run_triage_for_project` (latest-scan_run resolution).
    """
    cancel_token = CancellationToken()
    triage_run_registry.register(
        scan_run_id=scan_run_id,
        project_id=project_id,
        cancel_token=cancel_token,
    )

    thread = threading.Thread(
        target=_run_triage,
        kwargs={
            "base_path": base_path,
            "project_name": project_name,
            "project_id": project_id,
            "scan_run_id": scan_run_id,
            "request": request,
            "holder_token": holder_token,
            "bus": bus,
            "cancel_token": cancel_token,
            "lock_registry": lock_registry or get_registry(),
            "tool_registry": tool_registry,
            "triage_run_registry": triage_run_registry,
            "is_resume": is_resume,
        },
        name=f"triage-run-{scan_run_id}",
        daemon=True,
    )
    thread.start()
    return thread


def _run_triage(
    *,
    base_path: str,
    project_name: str,
    project_id: int,
    scan_run_id: int,
    request: TriageRequest,
    holder_token: str,
    bus: EventBus,
    cancel_token: CancellationToken,
    lock_registry: LockRegistry,
    tool_registry: ToolRegistry,
    triage_run_registry: TriageRunRegistry,
    is_resume: bool = False,
) -> None:
    del request  # finding-scoped triage is reserved for a later phase
    try:
        sink = EventBusTriageSink(bus)
        try:
            if is_resume:
                resume_triage_for_project(
                    project_name,
                    project_id=project_id,
                    scan_run_id=scan_run_id,
                    tool_registry=tool_registry,
                    event_sink=sink,
                    cancel_token=cancel_token,
                    app_root=Path(base_path),
                )
            else:
                run_triage_for_project(
                    project_name,
                    project_id=project_id,
                    tool_registry=tool_registry,
                    event_sink=sink,
                    cancel_token=cancel_token,
                    app_root=Path(base_path),
                )
        except TriageCancelled:
            logger.info("triage scan_run_id=%d cancelled", scan_run_id)
        except NoScanRunError:
            # Should be unreachable: the start endpoint validated this
            # before spawning the worker. Log and swallow.
            logger.warning(
                "triage scan_run_id=%d aborted: no scan_runs exist",
                scan_run_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("triage scan_run_id=%d failed", scan_run_id)
    finally:
        triage_run_registry.unregister(scan_run_id)
        try:
            lock_registry.release_job("triage", holder_token)
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
