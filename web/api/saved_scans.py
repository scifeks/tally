"""Project-scoped routes for saved scans."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request, Response

from application.ports.saved_scans import SavedScanNameConflict
from application.saved_scans.service import (
    SavedScanNotFound,
    SavedScansService,
    SavedScanValidationError,
)
from core.project_paths import ProjectPaths
from domain.saved_scans.entry import (
    SavedScanArgProfileRef,
    SavedScanHydrated,
    SavedScanListItem,
    SavedScanRepoRef,
    SavedScanToolRef,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)
from web.api._errors import Conflict, NotFound
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api.saved_scans_schemas import (
    SavedScanArgProfileResponse,
    SavedScanDetailResponse,
    SavedScanListItemResponse,
    SavedScanListResponse,
    SavedScanRepoResponse,
    SavedScanToolResponse,
    SavedScanWriteRequest,
)

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
            arg_profile_ids=body.arg_profile_ids,
        )
    except SavedScanNotFound as exc:
        raise NotFound(str(exc)) from exc
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
