"""Shared batch creation for auto-triage and MCP triage."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.triage.batching import (
    batch_size_for_segment,
    compute_batches,
)
from domain.pipeline.triage_events import BatchCreated

if TYPE_CHECKING:
    from application.ports.triage_batch_repository import (
        TriageBatchRepositoryPort,
    )
    from application.ports.triage_event_sink import TriageEventSink
    from application.tools.registry import ToolRegistry

_log = logging.getLogger(__name__)


def create_triage_batches(
    *,
    run_id: int,
    triage_repo: TriageBatchRepositoryPort,
    tool_registry: ToolRegistry,
    max_findings_per_batch: int = 4,
    event_sink: TriageEventSink | None = None,
    project_id: int | None = None,
) -> list[tuple[int, int]]:
    """Create triage batches for a scan run.

    Returns ``[(batch_id, finding_count), ...]``.
    """
    stale = triage_repo.cancel_remaining(run_id)
    if stale:
        _log.info(
            "Cancelled %d stale batches for run_id=%d",
            stale,
            run_id,
        )

    skip_tools = frozenset(
        t.name for t in tool_registry.get_all_tools() if getattr(t, "skip", False)
    )
    combos = triage_repo.get_active_finding_combos(run_id, skip_tools)

    all_created: list[tuple[int, int]] = []
    for tool, repo, segment in combos:
        try:
            findings = triage_repo.fetch_active_findings_for_batching(
                run_id, tool, repo, segment
            )
            batches = compute_batches(
                findings,
                max_findings_per_batch=batch_size_for_segment(
                    segment, default=max_findings_per_batch
                ),
            )
            created = triage_repo.create_batches(run_id, batches)
            _log.info(
                "Created %d batches: tool=%s repo=%s segment=%s",
                len(created),
                tool,
                repo,
                segment,
            )
            if event_sink:
                for batch_id, count in created:
                    event_sink.emit(
                        BatchCreated(
                            scan_run_id=run_id,
                            project_id=project_id,
                            batch_id=batch_id,
                            segment=segment,
                            findings_count=count,
                            message=(
                                f"Batched {count} finding(s)"
                                f" for {tool}/{repo}/{segment}"
                            ),
                        )
                    )
            all_created.extend(created)
        except Exception as exc:
            raise RuntimeError(
                f"Batching failed for {tool}/{repo}/{segment}: {exc}"
            ) from exc
    return all_created
