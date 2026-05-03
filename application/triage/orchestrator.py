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
    from application.tools.registry import ToolRegistry


def _retry_once[T](fn: Callable[[], T]) -> T:
    """Call fn; on FindingsBusy sleep 5 s and retry once, then re-raise."""
    try:
        return fn()
    except FindingsBusy:
        time.sleep(5)
        return fn()


def run_triage(project: str, tool_registry: ToolRegistry) -> dict[str, int]:
    """Run AI triage sessions for untriaged findings."""
    runner = TriageRunner.for_project(project, tool_registry)
    return dataclasses.asdict(_retry_once(runner.run))


def run_triage_batch_only(project: str, tool_registry: ToolRegistry) -> int:
    """Run only the batching phase. No MCP server, no Claude sessions."""
    runner = TriageRunner.for_project(project, tool_registry)
    _run_id, total = runner.batch()
    return total


def run_triage_dry_run(project: str, tool_registry: ToolRegistry) -> int:
    """Batch phase + render prompts to DEBUG log. No MCP server, no Claude."""
    runner = TriageRunner.for_project(project, tool_registry)
    return _retry_once(runner.run_dry_run)


def run_triage_for_project(
    project: str,
    *,
    project_id: int,
    tool_registry: ToolRegistry,
    event_sink: TriageEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    app_root: Path | None = None,
    scan_run_id: int | None = None,
    holder_token: str | None = None,
) -> dict[str, int]:
    """Service-path entry: full triage with sink + cancel token wired in.

    Resolves the latest scan_run for the project's findings.db and
    triages it. The caller (``TriageService.start_triage``) owns the
    Tier-1 ``triage`` job lock. ``holder_token`` is forwarded to
    ``TriageRunner.run`` so per-batch finding-id locks acquire under
    the same identity, blocking analyst PATCHes for the duration of
    each batch.
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
        tool_registry=tool_registry,
    )
    return dataclasses.asdict(
        _retry_once(lambda: runner.run(holder_token=holder_token))
    )


def resume_triage_for_project(
    project: str,
    *,
    project_id: int,
    scan_run_id: int,
    tool_registry: ToolRegistry,
    event_sink: TriageEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    app_root: Path | None = None,
    holder_token: str | None = None,
) -> dict[str, int]:
    """Service-path entry: explicit resume of an existing triage run.

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
        tool_registry=tool_registry,
    )
    return dataclasses.asdict(
        _retry_once(lambda: runner.run(holder_token=holder_token))
    )


if __name__ == "__main__":
    import argparse

    from application.tools.registry import ToolRegistry, discover_tools

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    _registry = ToolRegistry()
    discover_tools(_registry)
    print(run_triage(args.project, _registry))
