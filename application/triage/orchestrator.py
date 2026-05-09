"""Triage application service: entry points delegating to TriageRunner."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import FindingsBusy

from .factory import build_triage_runner

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


def run_triage(
    project: str, tool_registry: ToolRegistry, *, app_root: Path
) -> dict[str, int]:
    """Run AI triage sessions for untriaged findings."""
    runner = build_triage_runner(project, tool_registry, app_root=app_root)
    return dataclasses.asdict(_retry_once(runner.run))


def run_triage_batch_only(
    project: str, tool_registry: ToolRegistry, *, app_root: Path
) -> int:
    """Builds batches without starting backend sessions."""
    runner = build_triage_runner(project, tool_registry, app_root=app_root)
    _run_id, total = runner.batch()
    return total


def run_triage_dry_run(
    project: str, tool_registry: ToolRegistry, *, app_root: Path
) -> int:
    """Logs prompts without starting backend sessions."""
    runner = build_triage_runner(project, tool_registry, app_root=app_root)
    return _retry_once(runner.run_dry_run)


def run_triage_for_project(
    project: str,
    *,
    project_id: int,
    tool_registry: ToolRegistry,
    event_sink: TriageEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    app_root: Path,
    scan_run_id: int | None = None,
    holder_token: str | None = None,
) -> dict[str, int]:
    """Service-path entry: full triage with sink + cancel token wired in."""
    runner = build_triage_runner(
        project,
        tool_registry,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        app_root=app_root,
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
    app_root: Path,
    holder_token: str | None = None,
) -> dict[str, int]:
    """Service-path entry: resume an existing triage run."""
    runner = build_triage_runner(
        project,
        tool_registry,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        reset_for_resume_scan_run_id=scan_run_id,
        app_root=app_root,
    )
    return dataclasses.asdict(
        _retry_once(lambda: runner.run(holder_token=holder_token))
    )


if __name__ == "__main__":
    import argparse

    from application.tools.registry import ToolRegistry, discover_tools

    _app_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    _registry = ToolRegistry()
    discover_tools(_registry)
    print(run_triage(args.project, _registry, app_root=_app_root))
