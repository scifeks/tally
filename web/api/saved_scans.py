"""Project-scoped routes for saved scans."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from application.locking import JobBusy
from application.ports.saved_scans import SavedScanNameConflict
from application.saved_scans.errors import StaleSavedScanError
from application.saved_scans.service import (
    SavedScanNotFound,
    SavedScansService,
    SavedScanValidationError,
)
from application.tools.registry import discover_tools
from application.tools.scan_service import get_scan_service
from core.project_paths import ProjectPaths
from domain.saved_scans.entry import (
    SavedScanArgProfileRef,
    SavedScanHydrated,
    SavedScanListItem,
    SavedScanRepoRef,
    SavedScanToolRef,
    StaleSavedScanArgProfileItem,
    StaleSavedScanItem,
    StaleSavedScanRepoItem,
    StaleSavedScanToolItem,
)
from factories.persistence import (
    create_finding_repo,
    create_repo_repo,
    create_url_finding_repo,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)
from infrastructure.store.repositories.tool_overrides import (
    ToolOverridesRepository,
)
from web.adapters.event_bus_scan_sink import EventBusScanSink
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter
from web.api._errors import Conflict, JobBusyError, NotFound, StaleSavedScan
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api._scan_run_summary import scan_run_to_summary
from web.api.saved_scans_schemas import (
    SavedScanArgProfileResponse,
    SavedScanDetailResponse,
    SavedScanListItemResponse,
    SavedScanListResponse,
    SavedScanRepoResponse,
    SavedScanToolResponse,
    SavedScanWriteRequest,
    StaleSavedScanArgProfileItemDetail,
    StaleSavedScanDetails,
    StaleSavedScanItemDetail,
    StaleSavedScanRepoItemDetail,
    StaleSavedScanToolItemDetail,
)
from web.api.schemas import ScanRunSummary

saved_scans_v1_router = APIRouter()


def _build_service(request: Request, project_id: int) -> SavedScansService:
    """Resolve the project and assemble the saved-scans service."""
    row = _resolve_project(request, project_id)
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    saved_scans_repo = SavedScansRepository(factory)
    profiles_repo = ToolArgProfilesRepository(factory)
    return SavedScansService(
        saved_scans_repo,
        profiles_repo,
        request.app.state.tool_registry,
    )


def _repo_to_response(ref: SavedScanRepoRef) -> SavedScanRepoResponse:
    return SavedScanRepoResponse(id=ref.id, name=ref.name, deleted_at=ref.deleted_at)


def _tool_to_response(ref: SavedScanToolRef) -> SavedScanToolResponse:
    return SavedScanToolResponse(tool_name=ref.tool_name)


def _arg_profile_to_response(
    ref: SavedScanArgProfileRef,
) -> SavedScanArgProfileResponse:
    return SavedScanArgProfileResponse(
        id=ref.id, tool_name=ref.tool_name, name=ref.name
    )


def _to_detail_response(hydrated: SavedScanHydrated) -> SavedScanDetailResponse:
    scan = hydrated.saved_scan
    return SavedScanDetailResponse(
        id=scan.id,
        name=scan.name,
        skip_enrichment=scan.skip_enrichment,
        repos=[_repo_to_response(r) for r in hydrated.repos],
        tools=[_tool_to_response(t) for t in hydrated.tools],
        skip_tool_ids=hydrated.skip_tool_names,
        segments=hydrated.segments,
        arg_profiles=[_arg_profile_to_response(p) for p in hydrated.arg_profiles],
        created_at=scan.created_at,
        updated_at=scan.updated_at,
    )


def _to_list_item_response(item: SavedScanListItem) -> SavedScanListItemResponse:
    scan = item.saved_scan
    return SavedScanListItemResponse(
        id=scan.id,
        name=scan.name,
        skip_enrichment=scan.skip_enrichment,
        repo_ids=item.repo_ids,
        tool_names=item.tool_names,
        skip_tool_ids=item.skip_tool_names,
        segments=item.segments,
        arg_profile_ids=item.arg_profile_ids,
        created_at=scan.created_at,
        updated_at=scan.updated_at,
    )


def _validation_error_to_envelope(exc: SavedScanValidationError) -> dict:
    """Translate a service SavedScanValidationError into envelope details."""
    return {
        "fields": [{"field": fe.field, "issue": fe.issue} for fe in exc.fields],
    }


@saved_scans_v1_router.get(
    "/{project_id}/saved-scans",
    response_model=SavedScanListResponse,
)
async def list_saved_scans(
    project_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> SavedScanListResponse:
    """List saved scans for a project."""
    service = await asyncio.to_thread(_build_service, request, project_id)
    rows, total = await asyncio.to_thread(service.list, offset=offset, limit=limit)
    return SavedScanListResponse(
        items=[_to_list_item_response(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@saved_scans_v1_router.get(
    "/{project_id}/saved-scans/{saved_scan_id}",
    response_model=SavedScanDetailResponse,
)
async def get_saved_scan(
    project_id: int,
    saved_scan_id: int,
    request: Request,
) -> SavedScanDetailResponse:
    """Return one saved scan with its joins hydrated."""
    service = await asyncio.to_thread(_build_service, request, project_id)
    hydrated = await asyncio.to_thread(service.get, saved_scan_id)
    if hydrated is None:
        raise NotFound(f"Saved scan id={saved_scan_id} not found")
    return _to_detail_response(hydrated)


@saved_scans_v1_router.post(
    "/{project_id}/saved-scans",
    response_model=SavedScanDetailResponse,
    status_code=201,
)
async def create_saved_scan(
    project_id: int,
    request: Request,
    body: SavedScanWriteRequest,
) -> SavedScanDetailResponse:
    """Create a new saved scan."""
    service = await asyncio.to_thread(_build_service, request, project_id)
    try:
        hydrated = await asyncio.to_thread(
            service.create,
            name=body.name,
            skip_enrichment=body.skip_enrichment,
            repo_ids=body.repo_ids,
            tool_names=body.tool_names,
            skip_tool_names=body.skip_tool_ids,
            segments=body.segments,
            arg_profile_ids=body.arg_profile_ids,
        )
    except SavedScanValidationError as exc:
        raise ApiValidationError(
            "Saved scan validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc
    except SavedScanNameConflict as exc:
        raise Conflict(str(exc)) from exc

    return _to_detail_response(hydrated)


@saved_scans_v1_router.put(
    "/{project_id}/saved-scans/{saved_scan_id}",
    response_model=SavedScanDetailResponse,
)
async def replace_saved_scan(
    project_id: int,
    saved_scan_id: int,
    request: Request,
    body: SavedScanWriteRequest,
) -> SavedScanDetailResponse:
    """Replace an existing saved scan."""
    service = await asyncio.to_thread(_build_service, request, project_id)
    try:
        hydrated = await asyncio.to_thread(
            service.replace,
            saved_scan_id,
            name=body.name,
            skip_enrichment=body.skip_enrichment,
            repo_ids=body.repo_ids,
            tool_names=body.tool_names,
            skip_tool_names=body.skip_tool_ids,
            segments=body.segments,
            arg_profile_ids=body.arg_profile_ids,
        )
    except SavedScanNotFound as exc:
        raise NotFound(f"Saved scan id={saved_scan_id} not found") from exc
    except SavedScanValidationError as exc:
        raise ApiValidationError(
            "Saved scan validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc
    except SavedScanNameConflict as exc:
        raise Conflict(str(exc)) from exc

    return _to_detail_response(hydrated)


@saved_scans_v1_router.delete(
    "/{project_id}/saved-scans/{saved_scan_id}",
    status_code=204,
)
async def delete_saved_scan(
    project_id: int,
    saved_scan_id: int,
    request: Request,
) -> Response:
    """Delete a saved scan; cascades the join tables via FK."""
    service = await asyncio.to_thread(_build_service, request, project_id)
    existing = await asyncio.to_thread(service.get, saved_scan_id)
    if existing is None:
        raise NotFound(f"Saved scan id={saved_scan_id} not found")
    await asyncio.to_thread(service.delete, saved_scan_id)
    return Response(status_code=204)


def _stale_items_to_envelope(
    items: tuple[StaleSavedScanItem, ...],
) -> list[dict[str, Any]]:
    """Translate domain stale items to the STALE_SAVED_SCAN wire shape."""
    parts: list[StaleSavedScanItemDetail] = []
    for item in items:
        if isinstance(item, StaleSavedScanRepoItem):
            parts.append(StaleSavedScanRepoItemDetail(id=item.id, name=item.name))
        elif isinstance(item, StaleSavedScanToolItem):
            parts.append(StaleSavedScanToolItemDetail(name=item.name))
        elif isinstance(item, StaleSavedScanArgProfileItem):
            parts.append(StaleSavedScanArgProfileItemDetail(id=item.id))
    return StaleSavedScanDetails(stale_items=parts).model_dump(by_alias=True)[
        "staleItems"
    ]


@saved_scans_v1_router.post(
    "/{project_id}/saved-scans/{saved_scan_id}/run",
    response_model=ScanRunSummary,
    status_code=202,
)
async def run_saved_scan(
    project_id: int,
    saved_scan_id: int,
    request: Request,
) -> ScanRunSummary:
    """Dispatch a saved scan; returns 202 with the new run summary."""
    row = _resolve_project(request, project_id)
    project_name = row.name
    base_path: str = request.app.state.base_path
    tool_registry = request.app.state.tool_registry

    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)

    overrides_repo = ToolOverridesRepository(factory)
    discover_tools(
        tool_registry,
        base_path,
        project_name=project_name,
        overrides_repo=overrides_repo,
    )

    saved_scans_repo = SavedScansRepository(factory)
    profiles_repo = ToolArgProfilesRepository(factory)
    saved_scans_service = SavedScansService(
        saved_scans_repo, profiles_repo, tool_registry
    )

    try:
        hydrated = await asyncio.to_thread(
            saved_scans_service.run_saved_scan, saved_scan_id
        )
    except SavedScanNotFound as exc:
        raise NotFound(f"Saved scan id={saved_scan_id} not found") from exc
    except StaleSavedScanError as exc:
        raise StaleSavedScan(_stale_items_to_envelope(exc.stale_items)) from exc

    run_repo = RunRepository(factory)
    chat_session_repo = ChatSessionRepository(factory)
    sink = EventBusScanSink(request.app.state.event_bus)

    repo_names = tuple(r.name for r in hydrated.repos)
    tool_names = tuple(t.tool_name for t in hydrated.tools)
    arg_profile_ids = [p.id for p in hydrated.arg_profiles]

    if hydrated.arg_profiles:
        registered = tool_registry.list_tool_names()
        display_to_id: dict[str, str] = {}
        for n in registered:
            display_to_id[n] = n
            display = n.replace("_", " ").replace("-", " ").title()
            display_to_id[display] = n

        profile_tools = {
            display_to_id.get(p.tool_name, p.tool_name) for p in hydrated.arg_profiles
        }
        tool_names = tuple(set(tool_names) | profile_tools)

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
            profiles_repo=profiles_repo,
            repo_ids=repo_names,
            tool_ids=tool_names,
            domains=tuple(hydrated.segments),
            skip_tool_ids=tuple(hydrated.skip_tool_names),
            skip_enrichment=hydrated.saved_scan.skip_enrichment,
            prompt=NoApprovalPromptAdapter(),
            event_sink=sink,
            arg_profile_ids=arg_profile_ids,
            saved_scan_id=saved_scan_id,
            finding_repo=finding_repo,
            repo_repo=repo_repo,
            url_finding_repo=url_finding_repo,
        )
    except JobBusy as exc:
        raise JobBusyError("scan", exc.current_holder) from exc

    fresh = await asyncio.to_thread(run_repo.get, handle.run_id)
    if fresh is None:
        raise NotFound(f"scan run {handle.run_id} not found after creation")
    return scan_run_to_summary(fresh)
