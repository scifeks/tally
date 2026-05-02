"""Triage application service: entry points delegating to TriageRunner."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from application.config.mcp_defaults import load_mcp_defaults
from application.locking import FindingsBusy

from .runner import TriageRunner

if TYPE_CHECKING:
    from application.locking.cancellation import CancellationToken
    from application.ports.triage_event_sink import TriageEventSink


def _retry_once[T](fn: Callable[[], T]) -> T:
    """Call fn; on FindingsBusy sleep 5 s and retry once, then re-raise."""
    try:
        return fn()
    except FindingsBusy:
        time.sleep(5)
        return fn()


def run_triage(project: str) -> dict[str, int]:
    """Run AI triage sessions for untriaged findings."""
    runner = TriageRunner.for_project(project)
    return dataclasses.asdict(_retry_once(runner.run))


def run_triage_batch_only(project: str) -> int:
    """Run only the batching phase. No MCP server, no Claude sessions."""
    runner = TriageRunner.for_project(project)
    _run_id, total = runner.batch()
    return total


def run_triage_dry_run(project: str) -> int:
    """Batch phase + render prompts to DEBUG log. No MCP server, no Claude."""
    runner = TriageRunner.for_project(project)
    return _retry_once(runner.run_dry_run)


def run_triage_for_project(
    project: str,
    *,
    project_id: int,
    event_sink: TriageEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    app_root: Path | None = None,
    scan_run_id: int | None = None,
) -> dict[str, int]:
    """Web-path entry: full triage with sink + cancel token wired in.

    Resolves the latest scan_run for the project's findings.db and
    triages it. Caller passes the project's integer id (used to stamp
    events with ``project_id``) and the dependencies that turn the
    runner into an SSE-emitting, cancellable worker. ``scan_run_id``
    pins the run to a specific id (e.g. for resume); when ``None``
    the runner picks the latest scan_run.
    """
    from .runner import _APP_ROOT

    root = app_root or _APP_ROOT
    from core.project_paths import ProjectPaths

    paths = ProjectPaths.from_canonical(root, project)
    if not paths.findings_db.exists():
        raise FileNotFoundError(f"Project database not found: {paths.findings_db}")
    from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent
    from infrastructure.store import make_store

    run_repo, _, triage_repo, audit_repo = make_store(root, project)

    _, _, session_timeout_seconds = load_mcp_defaults(str(root))
    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        root,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        triage_agent=ClaudeTriageAgent(),
        session_timeout_seconds=session_timeout_seconds,
    )
    return dataclasses.asdict(_retry_once(runner.run))


def resume_triage_for_project(
    project: str,
    *,
    project_id: int,
    scan_run_id: int,
    event_sink: TriageEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    app_root: Path | None = None,
) -> dict[str, int]:
    """Web-path entry: explicit resume of an existing triage run.

    Flips stranded ``in_progress`` and retryable ``failed`` batches
    back to ``pending`` (via ``TriageBatchRepository.reset_for_resume``)
    before running, so ``claim_batch`` can pick them up. ``scan_run_id``
    is mandatory; there is no "resume the latest run" semantic.
    """
    from .runner import _APP_ROOT

    root = app_root or _APP_ROOT
    from core.project_paths import ProjectPaths

    paths = ProjectPaths.from_canonical(root, project)
    if not paths.findings_db.exists():
        raise FileNotFoundError(f"Project database not found: {paths.findings_db}")
    from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent
    from infrastructure.store import make_store

    run_repo, _, triage_repo, audit_repo = make_store(root, project)
    triage_repo.reset_for_resume(scan_run_id)

    _, _, session_timeout_seconds = load_mcp_defaults(str(root))
    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        root,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        triage_agent=ClaudeTriageAgent(),
        session_timeout_seconds=session_timeout_seconds,
    )
    return dataclasses.asdict(_retry_once(runner.run))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    print(run_triage(args.project))
