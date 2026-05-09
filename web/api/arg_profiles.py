"""Project-scoped routes for tool argument profiles."""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response
from starlette.datastructures import FormData, UploadFile

from application.ports.arg_files_storage import ArgFileNameError
from application.ports.tool_arg_profiles import ToolArgProfileNameConflict
from application.tool_arg_profiles.service import (
    FileArgInput,
    FlagArgInput,
    ProfileArgInput,
    StringArgInput,
    ToolArgProfileNotFound,
    ToolArgProfilesService,
    ToolArgProfileValidationError,
)
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
from web.api._errors import Conflict, NotFound, PathTraversal
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api.arg_profiles_schemas import (
    ArgProfileArgResponse,
    ArgProfileFileArgResponse,
    ArgProfileFlagArgResponse,
    ArgProfileListResponse,
    ArgProfilePayload,
    ArgProfilePayloadFileArg,
    ArgProfilePayloadFlagArg,
    ArgProfilePayloadStringArg,
    ArgProfileResponse,
    ArgProfileStringArgResponse,
    parse_arg_profile_payload,
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
        return ArgProfileStringArgResponse(
            name=arg.name,
            value=arg.value,
            operator=arg.operator,
        )
    assert isinstance(arg, ToolArgProfileFileArg)
    url = (
        _build_download_url(project_id, profile_id, arg.name)
        if with_download_url
        else None
    )
    return ArgProfileFileArgResponse(
        name=arg.name,
        path=arg.path,
        operator=arg.operator,
        original_filename=arg.original_filename,
        download_url=url,
    )


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


async def _build_inputs(
    payload: ArgProfilePayload,
    form: FormData,
    *,
    allow_keep_existing: bool,
) -> list[ProfileArgInput]:
    """Pair payload file-args with multipart uploads to build service inputs.

    PUT treats a missing upload as keep-existing; POST collects every
    missing arg name into a single 422 envelope.
    """
    inputs: list[ProfileArgInput] = []
    missing_files: list[dict[str, str]] = []
    for arg in payload.args:
        if isinstance(arg, ArgProfilePayloadFlagArg):
            inputs.append(FlagArgInput(name=arg.name))
            continue
        if isinstance(arg, ArgProfilePayloadStringArg):
            inputs.append(
                StringArgInput(
                    name=arg.name,
                    value=arg.value,
                    operator=arg.operator,
                )
            )
            continue
        assert isinstance(arg, ArgProfilePayloadFileArg)
        upload = form.get(arg.name)
        if isinstance(upload, UploadFile):
            data = await upload.read()
            inputs.append(
                FileArgInput(
                    name=arg.name,
                    data=data,
                    original_filename=upload.filename,
                    operator=arg.operator,
                )
            )
        elif allow_keep_existing:
            inputs.append(
                FileArgInput(
                    name=arg.name,
                    data=None,
                    operator=arg.operator,
                )
            )
        else:
            missing_files.append({"field": arg.name, "issue": "missing upload field"})
    if missing_files:
        raise ApiValidationError(
            "Arg profile payload references files that were not uploaded",
            details={"fields": missing_files},
        )
    return inputs


def _validation_error_to_envelope(exc: ToolArgProfileValidationError) -> dict:
    """Translate a service ToolArgProfileValidationError into envelope details."""
    return {
        "fields": [{"field": fe.field, "issue": fe.issue} for fe in exc.fields],
    }


@arg_profiles_v1_router.get(
    "/{project_id}/arg-profiles",
    response_model=ArgProfileListResponse,
    response_model_exclude_none=True,
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


@arg_profiles_v1_router.post(
    "/{project_id}/arg-profiles",
    response_model=ArgProfileResponse,
    status_code=201,
)
async def create_arg_profile(
    project_id: int,
    request: Request,
) -> ArgProfileResponse:
    """Create a new arg profile via multipart upload."""
    form = await request.form()
    payload_field = form.get("payload")
    if not isinstance(payload_field, str):
        raise ApiValidationError("payload form field is required")
    parsed = parse_arg_profile_payload(payload_field)
    inputs = await _build_inputs(parsed, form, allow_keep_existing=False)

    service, _saved_scans_repo, _paths = await asyncio.to_thread(
        _build_service, request, project_id
    )
    try:
        profile = await asyncio.to_thread(
            service.create,
            tool_name=parsed.tool_name,
            name=parsed.name,
            args=inputs,
        )
    except ToolArgProfileValidationError as exc:
        raise ApiValidationError(
            "Arg profile validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc
    except ToolArgProfileNameConflict as exc:
        raise Conflict(str(exc)) from exc
    except ArgFileNameError as exc:
        raise PathTraversal(str(exc)) from exc

    return _to_response(profile, project_id, with_download_url=True)


@arg_profiles_v1_router.put(
    "/{project_id}/arg-profiles/{profile_id}",
    response_model=ArgProfileResponse,
)
async def replace_arg_profile(
    project_id: int,
    profile_id: int,
    request: Request,
) -> ArgProfileResponse:
    """Replace an arg profile via multipart upload."""
    form = await request.form()
    payload_field = form.get("payload")
    if not isinstance(payload_field, str):
        raise ApiValidationError("payload form field is required")
    parsed = parse_arg_profile_payload(payload_field)
    inputs = await _build_inputs(parsed, form, allow_keep_existing=True)

    service, _saved_scans_repo, _paths = await asyncio.to_thread(
        _build_service, request, project_id
    )
    try:
        profile = await asyncio.to_thread(
            service.replace,
            profile_id,
            tool_name=parsed.tool_name,
            name=parsed.name,
            args=inputs,
        )
    except ToolArgProfileNotFound as exc:
        raise NotFound(f"Arg profile id={profile_id} not found") from exc
    except ToolArgProfileValidationError as exc:
        raise ApiValidationError(
            "Arg profile validation failed",
            details=_validation_error_to_envelope(exc),
        ) from exc
    except ToolArgProfileNameConflict as exc:
        raise Conflict(str(exc)) from exc
    except ArgFileNameError as exc:
        raise PathTraversal(str(exc)) from exc

    return _to_response(profile, project_id, with_download_url=True)


@arg_profiles_v1_router.get(
    "/{project_id}/arg-profiles/{profile_id}/files/{arg_name}",
)
async def download_arg_file(
    project_id: int,
    profile_id: int,
    arg_name: str,
    request: Request,
) -> Response:
    """Stream the bytes of a file-type arg."""
    service, _saved_scans_repo, _paths = await asyncio.to_thread(
        _build_service, request, project_id
    )
    try:
        data = await asyncio.to_thread(service.read_file_arg, profile_id, arg_name)
    except ArgFileNameError as exc:
        raise PathTraversal(str(exc)) from exc
    if data is None:
        raise NotFound(
            f"No file persisted for arg {arg_name!r} on profile {profile_id}"
        )
    disp_name = arg_name
    profile = await asyncio.to_thread(service.get, profile_id)
    if profile:
        for a in profile.args:
            if isinstance(a, ToolArgProfileFileArg) and a.name == arg_name:
                disp_name = a.original_filename or arg_name
                break
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": (f'inline; filename="{disp_name}"')},
    )


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
