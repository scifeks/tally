"""Project-scoped routes for tool argument profiles (read and delete)."""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response

from application.tool_arg_profiles.service import ToolArgProfilesService
from core.project_paths import ProjectPaths
from domain.tool_arg_profiles.entry import (
    ToolArgProfile,
    ToolArgProfileArg,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)
from infrastructure.storage.arg_files import ArgFilesStorageAdapter
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)
from web.api._errors import Conflict, NotFound
from web.api._project_resolver import _resolve_project
from web.api.arg_profiles_schemas import (
    ArgProfileArgResponse,
    ArgProfileFileArgResponse,
    ArgProfileFlagArgResponse,
    ArgProfileListResponse,
    ArgProfileResponse,
    ArgProfileStringArgResponse,
)

arg_profiles_v1_router = APIRouter()


def _build_service(
    request: Request, project_id: int
) -> tuple[ToolArgProfilesService, SavedScansRepository, ProjectPaths]:
    """Build service layer and return with saved scans repo and paths."""
    row = _resolve_project(request, project_id)
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    profiles_repo = ToolArgProfilesRepository(factory)
    storage = ArgFilesStorageAdapter(paths.arg_files_dir)
    saved_scans_repo = SavedScansRepository(factory)
    return (
        ToolArgProfilesService(profiles_repo, storage),
        saved_scans_repo,
        paths,
    )


def _build_download_url(project_id: int, profile_id: int, arg_name: str) -> str:
    """Build the download URL for a file arg."""
    return (
        f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}"
        f"/files/{quote(arg_name, safe='')}"
    )


def _arg_to_response(
    arg: ToolArgProfileArg,
    project_id: int,
    profile_id: int,
    *,
    with_download_url: bool,
) -> ArgProfileArgResponse:
    """Convert a domain arg to its response model."""
    if isinstance(arg, ToolArgProfileFlagArg):
        return ArgProfileFlagArgResponse(name=arg.name)
    if isinstance(arg, ToolArgProfileStringArg):
        return ArgProfileStringArgResponse(name=arg.name, value=arg.value)
    assert isinstance(arg, ToolArgProfileFileArg)
    url = (
        _build_download_url(project_id, profile_id, arg.name)
        if with_download_url
        else None
    )
    return ArgProfileFileArgResponse(name=arg.name, path=arg.path, download_url=url)


def _to_response(
    profile: ToolArgProfile, project_id: int, *, with_download_url: bool
) -> ArgProfileResponse:
    """Convert a domain profile to its response model."""
    return ArgProfileResponse(
        id=profile.id,
        tool_name=profile.tool_name,
        name=profile.name,
        args=[
            _arg_to_response(
                a, project_id, profile.id, with_download_url=with_download_url
            )
            for a in profile.args
        ],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@arg_profiles_v1_router.get(
    "/{project_id}/arg-profiles",
    response_model=ArgProfileListResponse,
)
async def list_arg_profiles(
    project_id: int,
    request: Request,
    tool_name: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> ArgProfileListResponse:
    """List arg profiles for a project, optionally filtered by tool name."""
    service, _saved_scans_repo, _paths = await asyncio.to_thread(
        _build_service, request, project_id
    )
    rows, total = await asyncio.to_thread(
        service.list, tool_name=tool_name, offset=offset, limit=limit
    )
    return ArgProfileListResponse(
        items=[_to_response(r, project_id, with_download_url=False) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@arg_profiles_v1_router.get(
    "/{project_id}/arg-profiles/{profile_id}",
    response_model=ArgProfileResponse,
)
async def get_arg_profile(
    project_id: int,
    profile_id: int,
    request: Request,
) -> ArgProfileResponse:
    """Return a single arg profile with downloadUrl for file args."""
    service, _saved_scans_repo, _paths = await asyncio.to_thread(
        _build_service, request, project_id
    )
    profile = await asyncio.to_thread(service.get, profile_id)
    if profile is None:
        raise NotFound(f"Arg profile id={profile_id} not found")
    return _to_response(profile, project_id, with_download_url=True)


@arg_profiles_v1_router.delete(
    "/{project_id}/arg-profiles/{profile_id}",
    status_code=204,
)
async def delete_arg_profile(
    project_id: int,
    profile_id: int,
    request: Request,
) -> Response:
    """Delete an arg profile and its file-arg directory."""
    service, saved_scans_repo, _paths = await asyncio.to_thread(
        _build_service, request, project_id
    )
    profile = await asyncio.to_thread(service.get, profile_id)
    if profile is None:
        raise NotFound(f"Arg profile id={profile_id} not found")
    refs = await asyncio.to_thread(
        saved_scans_repo.find_referencing_arg_profile, profile_id
    )
    if refs:
        raise Conflict(
            "Arg profile is referenced by one or more saved scans",
            code="IN_USE",
            details={
                "savedScanIds": [r.id for r in refs],
                "savedScanNames": [r.name for r in refs],
            },
        )
    await asyncio.to_thread(service.delete, profile_id)
    return Response(status_code=204)
