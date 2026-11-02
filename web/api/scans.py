"""Scan lifecycle endpoints: config, start, history, detail,
cancel, resume, and SSE event stream."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from application.anthropic.mode_availability import BackgroundModeAvailabilityService
from application.locking import JobBusy
from application.mcp.ingest_service import McpIngestService
from application.project.repositories_service import ProjectRepositoriesService
from application.scans.background_launcher import ScanBackgroundLauncher
from application.scans.scans_service import (
    ScanNotCancellable,
    ScanNotFound,
    ScansService,
    ScanValidationError,
)
from application.tools.registry import discover_tools
from core.config import ConfigManager
from core.project_paths import ProjectPaths
from domain.pipeline.bus_event import EOS, BusEvent, new_event_id
from domain.scans.entry import ScanRunRow, ToolRunRow
from domain.scans.vuln_scanner_registry import (
    UnknownScannerSkill,
    group_by_family,
    list_scanners,
    resolve_display_slug,
)
from domain.tools.scan_types import SEGMENT_ORDER
from factories.persistence import (
    ProjectNotFound,
    create_arg_profiles_repo,
    create_finding_repo,
    create_overrides_repo,
    create_repo_repo,
    create_scan_repos,
    create_scans_service,
    create_url_finding_repo,
    load_active_repos,
)
from factories.scanning import create_git_diff, get_scan_service
from web.adapters.event_bus_scan_sink import EventBusScanSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
from web.api._errors import (
    BadRequest,
    Conflict,
    JobBusyError,
    NotFound,
)
from web.api._errors import (
    ValidationError as ApiValidationError,
)
from web.api._project_resolver import _resolve_project
from web.api._scan_run_summary import scan_run_to_summary
from web.api.schemas import (
    BackgroundScanResumeRequest,
    BackgroundScanStartResponse,
    ScanCancelAllResponse,
    ScanCancelResponse,
    ScanConfigRepo,
    ScanConfigResponse,
    ScanConfigTool,
    ScanDetailResponse,
    ScannerSkillItem,
    ScanProgressResponse,
    ScanRunSummary,
    ScansListResponse,
    ScanStartRequest,
    ToolRunItem,
    ToolRunsSummary,
)
from web.sse import format_sse_frame

logger = logging.getLogger("tally.web.scans")


# All routes are project-scoped under /api/v1/projects/...
v1_router = APIRouter()


def _service(request: Request, project_id: int) -> ScansService:
    """Build a ScansService for *project_id* or raise 404."""
    try:
        return create_scans_service(request.app.state.project_registry, project_id)
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _tool_run_to_item(row: ToolRunRow) -> ToolRunItem:
    duration: float | None = None
    if row.started_at and row.finished_at:
        try:
            start = datetime.fromisoformat(row.started_at)
            end = datetime.fromisoformat(row.finished_at)
            duration = (end - start).total_seconds()
        except ValueError:
            duration = None
    return ToolRunItem(
        id=row.id,
        run_id=row.run_id,
        tool=row.tool,
        repo=row.repo,
        domain=row.domain,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration=duration,
        findings_count=row.findings_count,
        enriched_count=row.enriched_count,
        total_to_enrich=row.total_to_enrich,
        exit_code=row.exit_code,
        skip_reason=row.skip_reason,
    )


def _validation_error_to_envelope(exc: ScanValidationError) -> dict:
    return {"fields": [{"field": fe.field, "issue": fe.issue} for fe in exc.fields]}


def _resolve_scanner_slugs(
    only: list[str],
    exclude: list[str],
) -> tuple[list[str], list[str]]:
    """Expand family names to display slugs and validate all entries.

    Accepts a mix of display slugs and family names. Family names are
    expanded to per-scanner display slugs via ``group_by_family()``.
    Returns deduplicated (only, exclude) display slug lists.
    """
    families = group_by_family()

    def _expand(items: list[str]) -> list[str]:
        result: list[str] = []
        for item in items:
            if item in families:
                result.extend(e.display_slug for e in families[item])
            else:
                resolve_display_slug(item)
                result.append(item)
        return list(dict.fromkeys(result))

    return _expand(only), _expand(exclude)


_RESUMABLE_STATUSES = frozenset({"failed", "running", "rate_limited"})

_BACKGROUND_ONLY_FIELDS = (
    "billing_method",
    "only_scanner_skills",
    "exclude_scanner_skills",
    "adversarial_verification",
)


def _build_background_launcher(
    request: Request,
    paths: ProjectPaths,
) -> ScanBackgroundLauncher:
    """Construct a ScanBackgroundLauncher for the given project."""
    base_path: str = request.app.state.base_path
    cfg = ConfigManager(base_path).global_config

    run_repo = create_scan_repos(paths.findings_db)[0]
    finding_repo = create_finding_repo(paths.findings_db)
    sink = EventBusScanSink(request.app.state.event_bus)
    mcp_service = McpIngestService(
        finding_repo=finding_repo,
        run_repo=run_repo,
        scan_event_sink=sink,
    )

    return ScanBackgroundLauncher(
        mcp_service=mcp_service,
        availability=BackgroundModeAvailabilityService(cfg),
        config=cfg,
        scan_phase_repo=mcp_service,
        scan_event_sink=sink,
        scan_run_status_repo=run_repo,
    )


def _validate_start_semantics(body: ScanStartRequest) -> None:
    """Raise BadRequest for semantic violations that Pydantic Literal
    types cannot express (mutual exclusion, interactive + background
    fields)."""
    if body.only_scanner_skills and body.exclude_scanner_skills:
        raise BadRequest(
            "only_scanner_skills and exclude_scanner_skills are mutually exclusive"
        )

    if body.interaction_mode == "interactive":
        present = [f for f in _BACKGROUND_ONLY_FIELDS if _field_is_set(body, f)]
        if present:
            raise BadRequest(
                f"{', '.join(present)} require interaction_mode='background'"
            )


def _field_is_set(body: ScanStartRequest, name: str) -> bool:
    """True when the field carries a non-default value."""
    val = getattr(body, name, None)
    if val is None:
        return False
    if isinstance(val, (list, str)) and not val:
        return False
    if isinstance(val, bool) and not val:
        return False
    return True


def _resolve_api_key_source(
    base_path: str,
    override: str | None,
) -> str | None:
    """Explicit override > config > None. Mirrors triage's pattern."""
    if override:
        return override
    cfg = ConfigManager(base_path).global_config
    return (cfg.claude.api_key if cfg.claude else None) or None


async def _schedule_launch(
    launcher: ScanBackgroundLauncher,
    run_repo: Any,
    run_id: int,
    **launch_kwargs: Any,
) -> None:
    """Transition the run to running and launch the worker.

    Marks the run ``running`` before the thread fires so the UI's
    active-scans filter picks it up immediately. On ValueError (caller
    validation failures surfaced by the launcher) the run is marked
    ``failed`` and a 400 is raised. Any other exception also marks the
    run ``failed`` so the row never stays stuck in ``queued`` /
    ``running`` without a worker; the error propagates as a 500.
    """
    await asyncio.to_thread(run_repo.set_status, run_id, "running")
    try:
        await asyncio.to_thread(launcher.launch, run_id=run_id, **launch_kwargs)
    except ValueError as exc:
        await asyncio.to_thread(run_repo.set_status, run_id, "failed")
        raise BadRequest(str(exc)) from exc
    except Exception:
        await asyncio.to_thread(run_repo.set_status, run_id, "failed")
        raise


def _build_progress(
    row: ScanRunRow, tool_runs: list[ToolRunRow]
) -> ScanProgressResponse:
    sp = ScansService.compute_progress(row, tool_runs)
    return ScanProgressResponse(
        id=row.id,
        status=row.status,
        progress=sp.progress,
        current_segment=None,
        segment_label=None,
        tool_runs_summary=ToolRunsSummary(
            queued=sp.counts.queued,
            running=sp.counts.running,
            done=sp.counts.done,
            failed=sp.counts.failed,
            skipped=sp.counts.skipped,
        ),
    )


# Project-scoped routes: literal segments first, then parameterized


@v1_router.get(
    "/{project_id}/scans/config",
    response_model=ScanConfigResponse,
)
async def get_scans_config(
    project_id: int,
    request: Request,
) -> ScanConfigResponse:
    """Return the inputs the SPA needs to compose a scan start
    request."""
    row = _resolve_project(request, project_id)

    base_path: str = request.app.state.base_path
    project_name: str = row.name
    tool_registry = request.app.state.tool_registry

    paths = ProjectPaths.from_registry_row(row)
    overrides_repo = create_overrides_repo(paths.findings_db)
    discover_tools(
        tool_registry,
        base_path,
        project_name=project_name,
        overrides_repo=overrides_repo,
    )

    repo_service = ProjectRepositoriesService.build(
        request.app.state.project_registry,
        request.app.state.base_path,
    )
    repos: list[ScanConfigRepo] = []
    for r in repo_service.list_active(project_id):
        assert isinstance(r.id, int)  # list_active filters to DB-resident repos
        service = r.services[0] if r.services else None
        if service is None:
            continue
        location = "docker" if service.container_name else "local"
        repos.append(
            ScanConfigRepo(
                id=r.id,
                name=r.name,
                source=",".join(service.type) or "unknown",
                location=location,
            )
        )

    tools: list[ScanConfigTool] = []
    for tw in tool_registry.get_all_tools():
        tools.append(
            ScanConfigTool(
                id=tw.name,
                name=tw.name.replace("_", " ").replace("-", " ").title(),
                domain=getattr(tw, "category", "") or "",
                enabled=True,
            )
        )

    scanner_skills: list[ScannerSkillItem] = []
    for entry in list_scanners():
        scanner_skills.append(
            ScannerSkillItem(
                slug=entry.display_slug,
                family=entry.family,
                description=entry.description,
            )
        )

    return ScanConfigResponse(
        repos=repos,
        tools=tools,
        domains=list(SEGMENT_ORDER),
        available_scanner_skills=scanner_skills,
    )


@v1_router.get("/{project_id}/scans/events")
async def scans_events(
    project_id: int,
    request: Request,
    run_id: int | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream for scan lifecycle events, with snapshot on connect
    to sync client state immediately."""
    service = _service(request, project_id)
    bus = request.app.state.event_bus
    sub_id, queue = await bus.subscribe("scan")

    snapshot_event = await _build_snapshot(service, project_id, run_id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield format_sse_frame(snapshot_event)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item is EOS:
                    break
                payload = item.payload
                if payload.get("project_id") != project_id:
                    continue
                if run_id is not None and payload.get("run_id") != run_id:
                    continue
                yield format_sse_frame(item)
        finally:
            await bus.unsubscribe("scan", sub_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v1_router.post(
    "/{project_id}/scans/cancel-all",
    response_model=ScanCancelAllResponse,
)
async def cancel_all_scans(
    project_id: int,
    request: Request,
) -> ScanCancelAllResponse:
    """Cancel every active scan for this project."""
    service = _service(request, project_id)
    cancelled = await asyncio.to_thread(service.cancel_all)
    return ScanCancelAllResponse(cancelled=cancelled)


@v1_router.get(
    "/{project_id}/scans",
    response_model=ScansListResponse,
)
async def list_scans(
    project_id: int,
    request: Request,
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ScansListResponse:
    """Paginated scan history for a project, newest-first."""
    service = _service(request, project_id)
    try:
        service.validate_status(status)
    except ScanValidationError as exc:
        raise ApiValidationError(
            "Scan query validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc
    repo = service.run_repo
    rows, total = await asyncio.to_thread(
        repo.list_for_project,
        project_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return ScansListResponse(
        items=[scan_run_to_summary(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.post(
    "/{project_id}/scans",
    response_model=ScanRunSummary | BackgroundScanStartResponse,
    status_code=202,
)
async def start_scan(
    project_id: int,
    request: Request,
    body: ScanStartRequest,
) -> ScanRunSummary | BackgroundScanStartResponse:
    """Queue a new scan in a worker thread.

    Returns 409 ``JOB_ALREADY_RUNNING`` if another scan is in progress
    (interactive mode only). Background mode dispatches via the Agent SDK.
    """
    _validate_start_semantics(body)

    if body.interaction_mode == "background":
        return await _start_background_scan(project_id, request, body)
    return await _start_interactive_scan(project_id, request, body)


async def _start_interactive_scan(
    project_id: int,
    request: Request,
    body: ScanStartRequest,
) -> ScanRunSummary:
    """Interactive scan path: existing tool-runner pipeline."""
    row = _resolve_project(request, project_id)
    project_name: str = row.name
    base_path: str = request.app.state.base_path
    tool_registry = request.app.state.tool_registry

    paths = ProjectPaths.from_registry_row(row)
    overrides_repo = create_overrides_repo(paths.findings_db)
    discover_tools(
        tool_registry,
        base_path,
        project_name=project_name,
        overrides_repo=overrides_repo,
    )

    repos_service = ProjectRepositoriesService.build(
        request.app.state.project_registry,
        request.app.state.base_path,
    )
    profiles_repo = create_arg_profiles_repo(paths.findings_db)
    service = _service(request, project_id)

    try:
        resolved = await asyncio.to_thread(
            service.validate_start_request,
            repo_ids=body.repoIds,
            tool_ids=body.toolIds,
            skip_tool_ids=body.skipToolIds,
            domains=body.domains,
            arg_profile_ids=body.argProfileIds,
            repos_service=repos_service,
            tool_registry=tool_registry,
            profiles_repo=profiles_repo,
        )
    except ScanValidationError as exc:
        raise ApiValidationError(
            "Scan validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc

    sink = EventBusScanSink(request.app.state.event_bus)
    run_repo, chat_session_repo, _, _ = create_scan_repos(paths.findings_db)
    finding_repo = create_finding_repo(paths.findings_db)
    repo_repo = create_repo_repo(paths.findings_db)
    url_finding_repo = create_url_finding_repo(paths.findings_db)

    try:
        handle = await asyncio.to_thread(
            get_scan_service().start_scan,
            project_id=project_id,
            project_name=project_name,
            base_path=base_path,
            tool_registry=tool_registry,
            run_repo=run_repo,
            chat_session_repo=chat_session_repo,
            finding_repo=finding_repo,
            repo_repo=repo_repo,
            url_finding_repo=url_finding_repo,
            profiles_repo=profiles_repo,
            repo_ids=tuple(resolved.repo_names),
            tool_ids=tuple(body.toolIds),
            domains=tuple(body.domains),
            skip_tool_ids=tuple(body.skipToolIds),
            skip_enrichment=body.skipEnrichment,
            arg_profile_ids=body.argProfileIds,
            since_commit=body.sinceCommit,
            git_diff=create_git_diff() if body.sinceCommit else None,
            prompt=NoApprovalPromptAdapter(),
            event_sink=sink,
        )
    except JobBusy as exc:
        raise JobBusyError("scan", exc.current_holder) from exc

    fresh = await asyncio.to_thread(service.run_repo.get, handle.run_id)
    if fresh is None:
        raise NotFound(f"scan run {handle.run_id} not found after creation")
    return scan_run_to_summary(fresh)


async def _start_background_scan(
    project_id: int,
    request: Request,
    body: ScanStartRequest,
) -> BackgroundScanStartResponse:
    """Background scan path: Agent SDK dispatch.

    Pre-checks (slug resolution, active-repo lookup) run before
    creating the run row so a validation failure cannot leave an
    orphaned "queued" row.
    """
    row = _resolve_project(request, project_id)
    project_name: str = row.name
    base_path: str = request.app.state.base_path
    paths = ProjectPaths.from_registry_row(row)

    # Pre-check: scanner slug resolution
    try:
        only, exclude = _resolve_scanner_slugs(
            body.only_scanner_skills, body.exclude_scanner_skills
        )
    except UnknownScannerSkill as exc:
        raise BadRequest(str(exc)) from exc

    # Pre-check: project has active repos
    repos = await asyncio.to_thread(load_active_repos, base_path, project_name)
    if not repos:
        raise BadRequest(f"project {project_name!r} has no active repos")

    api_key = _resolve_api_key_source(base_path, body.api_key_override)

    # All cheap checks passed; create the run row
    run_repo = create_scan_repos(paths.findings_db)[0]
    run_id = await asyncio.to_thread(
        run_repo.create,
        project_id=project_id,
        repo_ids=[],
        tool_ids=["claudecode"],
        domains=["llm"],
        skip_enrichment=True,
        status="queued",
    )

    launcher = _build_background_launcher(request, paths)
    await _schedule_launch(
        launcher,
        run_repo,
        run_id,
        project_name=project_name,
        base_path=base_path,
        interaction_mode="background",
        billing_method=body.billing_method,
        only=only or None,
        exclude=exclude or None,
        adversarial=body.adversarial_verification,
        api_key_source=api_key,
    )

    return BackgroundScanStartResponse(
        id=run_id,
        project_id=project_id,
        status="queued",
        interaction_mode="background",
    )


@v1_router.post(
    "/{project_id}/scans/{run_id}/cancel",
    response_model=ScanCancelResponse,
    status_code=202,
)
async def cancel_scan(
    project_id: int,
    run_id: int,
    request: Request,
) -> ScanCancelResponse:
    """Request cancellation of a specific scan run."""
    service = _service(request, project_id)
    try:
        await asyncio.to_thread(service.cancel_scan, run_id)
    except ScanNotFound as exc:
        raise NotFound(f"scan run {run_id} not found") from exc
    except ScanNotCancellable as exc:
        raise Conflict(
            f"scan run {run_id} is not in a cancellable state",
            code="SCAN_NOT_CANCELLABLE",
            details={"status": exc.status},
        ) from exc
    return ScanCancelResponse(id=run_id, status="cancelling")


@v1_router.post(
    "/{project_id}/scans/{run_id}/resume",
    response_model=BackgroundScanStartResponse,
    status_code=202,
)
async def resume_scan(
    project_id: int,
    run_id: int,
    request: Request,
    body: BackgroundScanResumeRequest,
) -> BackgroundScanStartResponse:
    """Resume a background scan that was interrupted or rate-limited.

    Re-launches the Agent SDK session for the same run_id. The launcher
    inspects phase status to build a resume preamble that skips already
    completed phases.
    """
    row = _resolve_project(request, project_id)
    project_name: str = row.name
    base_path: str = request.app.state.base_path
    paths = ProjectPaths.from_registry_row(row)

    # Verify the run exists, belongs to this project, and is resumable
    run_repo = create_scan_repos(paths.findings_db)[0]
    scan_row = await asyncio.to_thread(run_repo.get, run_id)
    if scan_row is None or scan_row.project_id != project_id:
        raise NotFound(f"scan run {run_id} not found")

    if scan_row.status not in _RESUMABLE_STATUSES:
        raise BadRequest(f"run {run_id} status is {scan_row.status!r}; cannot resume")

    # Read the existing scan config to get only/exclude/adversarial
    finding_repo = create_finding_repo(paths.findings_db)
    mcp_service = McpIngestService(
        finding_repo=finding_repo,
        run_repo=run_repo,
    )
    scan_config = mcp_service.get_scan_config(project=project_name, run_id=run_id)
    only = scan_config.get("only") or None
    exclude = scan_config.get("exclude") or None
    adversarial = scan_config.get("adversarial_verification", False)

    api_key = _resolve_api_key_source(base_path, body.api_key_override)

    launcher = _build_background_launcher(request, paths)
    await _schedule_launch(
        launcher,
        run_repo,
        run_id,
        project_name=project_name,
        base_path=base_path,
        interaction_mode="background",
        billing_method=body.billing_method,
        only=only,
        exclude=exclude,
        adversarial=adversarial,
        api_key_source=api_key,
    )

    return BackgroundScanStartResponse(
        id=run_id,
        project_id=project_id,
        status="running",
        interaction_mode="background",
    )


@v1_router.get(
    "/{project_id}/scans/{run_id}/progress",
    response_model=ScanProgressResponse,
)
async def scan_progress(
    project_id: int,
    run_id: int,
    request: Request,
) -> ScanProgressResponse:
    """Point-in-time progress snapshot for a single scan run."""
    service = _service(request, project_id)
    repo = service.run_repo
    bundle = await asyncio.to_thread(repo.get_with_tool_runs, run_id)
    if bundle is None:
        raise NotFound(f"scan run {run_id} not found")
    scan_row, tool_rows = bundle
    if scan_row.project_id != project_id:
        raise NotFound(f"scan run {run_id} not found")
    return _build_progress(scan_row, tool_rows)


@v1_router.get(
    "/{project_id}/scans/{run_id}",
    response_model=ScanDetailResponse,
)
async def get_scan(
    project_id: int,
    run_id: int,
    request: Request,
) -> ScanDetailResponse:
    """Full scan run with the per-tool execution records."""
    service = _service(request, project_id)
    repo = service.run_repo
    bundle = await asyncio.to_thread(repo.get_with_tool_runs, run_id)
    if bundle is None:
        raise NotFound(f"scan run {run_id} not found")
    scan_row, tool_rows = bundle
    if scan_row.project_id != project_id:
        raise NotFound(f"scan run {run_id} not found")
    return ScanDetailResponse(
        id=scan_row.id,
        project_id=scan_row.project_id,
        status=scan_row.status,
        started_at=scan_row.started_at,
        finished_at=scan_row.finished_at,
        repo_ids=scan_row.repo_ids,
        tool_ids=scan_row.tool_ids,
        domains=scan_row.domains,
        findings_count=scan_row.findings_count,
        skip_enrichment=scan_row.skip_enrichment,
        tool_runs=[_tool_run_to_item(r) for r in tool_rows],
    )


async def _build_snapshot(
    service: ScansService,
    project_id: int,
    run_id: int | None,
) -> BusEvent:
    """Build a 'snapshot' BusEvent for the SSE on-connect frame."""
    payload: dict[str, Any] = {
        "run_id": run_id,
        "project_id": project_id,
    }
    if run_id is not None:
        bundle = await asyncio.to_thread(service.run_repo.get_with_tool_runs, run_id)
        if bundle is not None:
            scan_row, tool_rows = bundle
            if scan_row.project_id == project_id:
                progress = _build_progress(scan_row, tool_rows)
                handle = service.peek_active_run(run_id)
                payload.update(
                    status=scan_row.status,
                    progress=progress.progress,
                    current_segment=None,
                    segment_label=None,
                    current_repo=handle.current_repo if handle else None,
                    current_tool=handle.current_tool if handle else None,
                    tool_runs=[_tool_run_to_item(r).model_dump() for r in tool_rows],
                    project_id=scan_row.project_id,
                    started_at=scan_row.started_at,
                )
    else:
        active_handles = service.list_active_runs()
        payload["active_run_ids"] = [h.run_id for h in active_handles]
        # Payload includes current (repo, tool) for each active run so
        # late subscribers can render the live label immediately.
        payload["active_runs"] = [
            {
                "run_id": h.run_id,
                "repo": h.current_repo,
                "tool": h.current_tool,
            }
            for h in active_handles
        ]

    return BusEvent(
        event_id=new_event_id(),
        job_id="scan",
        stream="scan",
        event_type="snapshot",
        payload=payload,
        ts=datetime.now(UTC),
    )
