"""Triage application service: entry points delegating to TriageRunner."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

from .factory import build_triage_runner

if TYPE_CHECKING:
    from application.locking.cancellation import CancellationToken
    from application.ports.audit_repository import (
        AuditRepositoryPort,
    )
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_batch_repository import (
        TriageBatchRepositoryPort,
    )
    from application.ports.triage_event_sink import TriageEventSink
    from application.tools.registry import ToolRegistry


def run_triage(
    project: str,
    tool_registry: ToolRegistry,
    *,
    app_root: Path,
    run_repo: RunRepositoryPort,
    finding_repo: FindingRepositoryPort,
    triage_repo: TriageBatchRepositoryPort,
    audit_repo: AuditRepositoryPort,
    repo_paths: dict[str, Path],
) -> dict[str, int]:
    """Run AI triage sessions for untriaged findings."""
    runner = build_triage_runner(
        project,
        tool_registry,
        app_root=app_root,
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    return dataclasses.asdict(runner.run())


def run_triage_batch_only(
    project: str,
    tool_registry: ToolRegistry,
    *,
    app_root: Path,
    run_repo: RunRepositoryPort,
    finding_repo: FindingRepositoryPort,
    triage_repo: TriageBatchRepositoryPort,
    audit_repo: AuditRepositoryPort,
    repo_paths: dict[str, Path],
) -> int:
    """Build batches without starting backend sessions."""
    runner = build_triage_runner(
        project,
        tool_registry,
        app_root=app_root,
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    _run_id, total = runner.batch()
    return total


def run_triage_dry_run(
    project: str,
    tool_registry: ToolRegistry,
    *,
    app_root: Path,
    run_repo: RunRepositoryPort,
    finding_repo: FindingRepositoryPort,
    triage_repo: TriageBatchRepositoryPort,
    audit_repo: AuditRepositoryPort,
    repo_paths: dict[str, Path],
) -> int:
    """Log prompts without starting backend sessions."""
    runner = build_triage_runner(
        project,
        tool_registry,
        app_root=app_root,
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    return runner.run_dry_run()


def run_triage_for_project(
    project: str,
    *,
    project_id: int,
    tool_registry: ToolRegistry,
    run_repo: RunRepositoryPort,
    finding_repo: FindingRepositoryPort,
    triage_repo: TriageBatchRepositoryPort,
    audit_repo: AuditRepositoryPort,
    repo_paths: dict[str, Path],
    event_sink: TriageEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    app_root: Path,
    scan_run_id: int | None = None,
    holder_token: str | None = None,
) -> dict[str, int]:
    """Service-path entry: full triage with sink + cancel."""
    runner = build_triage_runner(
        project,
        tool_registry,
        event_sink=event_sink,
        cancel_token=cancel_token,
        project_id=project_id,
        scan_run_id=scan_run_id,
        app_root=app_root,
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    return dataclasses.asdict(runner.run(holder_token=holder_token))


def resume_triage_for_project(
    project: str,
    *,
    project_id: int,
    scan_run_id: int,
    tool_registry: ToolRegistry,
    run_repo: RunRepositoryPort,
    finding_repo: FindingRepositoryPort,
    triage_repo: TriageBatchRepositoryPort,
    audit_repo: AuditRepositoryPort,
    repo_paths: dict[str, Path],
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
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    return dataclasses.asdict(runner.run(holder_token=holder_token))
