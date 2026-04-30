"""Project API endpoints — v1 versioned routes.

The server is project-agnostic: ``/api/v1/projects`` returns the full
project list (auth-only); per-project routes resolve their target via
the path ``:project_id`` and the project registry.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from application.project.manager import ProjectManager
from core.config.manager import ConfigManager
from core.config.schemas import Repository
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from web.api._errors import NotFound
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    ProjectInfoPatchRequest,
    ProjectInfoResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectMetaResponse,
    RepoAuthPatchRequest,
    RepositoryItem,
    RepositoryListResponse,
)

# v1 router
v1_router = APIRouter()


def _count_url_findings(paths: ProjectPaths) -> int:
    """Count active url_findings rows; returns 0 on any error or missing DB."""
    if not paths.findings_db.exists():
        return 0
    try:
        factory = ConnectionFactory(paths.findings_db)
        with factory.connect() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='url_findings'"
            )
            if cur.fetchone() is None:
                return 0
            row = conn.execute(
                "SELECT COUNT(*) FROM url_findings uf "
                "JOIN repositories r ON r.id = uf.repo_id "
                "WHERE r.deleted_at IS NULL"
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def _load_project_tool_ids(commands_path: Path) -> list[str]:
    """Return sorted tool IDs from a project's commands.json, or [] if absent."""
    if not commands_path.exists():
        return []
    try:
        with open(commands_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return sorted(data.keys())


async def _count_findings(paths: ProjectPaths) -> int:
    if not paths.findings_db.exists():
        return 0
    factory = ConnectionFactory(paths.findings_db)

    def _query(f: ConnectionFactory) -> int:
        try:
            with f.connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM findings").fetchone()
                return row[0]
        except Exception:
            return 0

    return await asyncio.to_thread(_query, factory)


@v1_router.get("", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> ProjectListResponse:
    """Return the full project list (auth-only).

    The SPA uses this to populate the project picker before any
    project is selected. No project context required.
    """
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    items: list[ProjectListItem] = []
    for row in registry.list_active():
        config = manager.get_project_info(row["name"])
        if config is None:
            continue
        items.append(
            ProjectListItem(
                id=int(row["id"]),
                name=config.project_name,
                code=config.abbreviation,
                created_at=config.created,
            )
        )
    total = len(items)
    return ProjectListResponse(
        items=items[offset : offset + limit],
        total=total,
        offset=offset,
        limit=limit,
    )


@v1_router.get("/{project_id}/meta", response_model=ProjectMetaResponse)
async def get_project_meta(
    project_id: int,
    request: Request,
) -> ProjectMetaResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    finding_count = await _count_findings(paths)
    url_list_count = await asyncio.to_thread(_count_url_findings, paths)
    enabled_tools = await asyncio.to_thread(_load_project_tool_ids, paths.commands_json)
    return ProjectMetaResponse(
        id=int(row["id"]),
        name=config.project_name,
        code=config.abbreviation,
        repo_count=len(config.repositories),
        url_list_count=url_list_count,
        finding_count=finding_count,
        enabled_tools=enabled_tools,
    )


def _build_project_info_response(
    row: dict,
    config,
    finding_count: int,
) -> ProjectInfoResponse:
    paths = ProjectPaths.from_registry_row(row)
    return ProjectInfoResponse(
        id=int(row["id"]),
        name=config.project_name,
        code=config.abbreviation,
        company_name=config.company_name,
        department_name=config.department_name,
        abbreviation=config.abbreviation,
        created_at=config.created,
        path=str(paths.root),
        repo_count=len(config.repositories),
        finding_count=finding_count,
    )


@v1_router.get("/{project_id}/info", response_model=ProjectInfoResponse)
async def get_project_info_endpoint(
    project_id: int,
    request: Request,
) -> ProjectInfoResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    finding_count = await _count_findings(paths)
    return _build_project_info_response(row, config, finding_count)


@v1_router.patch("/{project_id}/info", response_model=ProjectInfoResponse)
async def patch_project_info(
    project_id: int,
    request: Request,
    body: ProjectInfoPatchRequest,
) -> ProjectInfoResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    project_name = row["name"]
    manager = ConfigManager(base_path)

    update: dict[str, str] = {}
    for field in ("company_name", "department_name", "abbreviation"):
        value = getattr(body, field)
        if value is not None:
            update[field] = value

    with manager.locked_project_config(project_name):
        config = manager.load_project_config(project_name)
        if config is None:
            raise NotFound(f"Project {project_id} not found")
        if update:
            config = config.model_copy(update=update)
            manager.save_project_config(project_name, config)

    paths = ProjectPaths.from_registry_row(row)
    finding_count = await _count_findings(paths)
    return _build_project_info_response(row, config, finding_count)


def _make_repo_repo(row: dict) -> RepositoryRepository:
    """Build a RepositoryRepository for the given project registry row."""
    paths = ProjectPaths.from_registry_row(row)
    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return RepositoryRepository(factory)


def _existing_endpoint_file(paths: ProjectPaths, repo: Repository) -> str | None:
    """Return the basename of the most-recent file under
    ``endpoints/<repo.uuid>/user_uploads/`` if any, else ``None``.

    Phase 9 stores user-uploaded endpoint specs under that directory; the
    presence of a file is the authoritative signal that a seed file is
    configured for the repo. Multiple files can coexist (replace-by-basename
    semantics); return the one most recently written.
    """
    if not repo.uuid:
        return None
    upload_dir = paths.endpoints_dir / repo.uuid / "user_uploads"
    if not upload_dir.exists():
        return None
    candidates = [p for p in upload_dir.iterdir() if p.is_file()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest.name


def _serialize_repo(
    repo: Repository,
    repo_id: int | None,
    *,
    paths: ProjectPaths | None = None,
) -> dict:
    """Dump a Repository to a JSON dict; strip auth; carry id and seed file."""
    data = repo.model_dump()
    data.pop("auth", None)
    data["id"] = repo_id
    data["endpoint_file"] = (
        _existing_endpoint_file(paths, repo) if paths is not None else None
    )
    return data


@v1_router.get(
    "/{project_id}/repositories",
    response_model=RepositoryListResponse,
)
async def list_repositories(
    project_id: int,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> JSONResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    repo_repo = _make_repo_repo(row)
    repos = config.repositories
    total = len(repos)
    page = repos[offset : offset + limit]
    items = []
    for repo in page:
        db_row = (
            repo_repo.get_by_uuid_including_deleted(repo.uuid) if repo.uuid else None
        )
        if db_row is not None and db_row.deleted_at is not None:
            continue
        repo_id = db_row.id if db_row is not None else None
        # DB name is the source of truth: name-only PATCHes rename the DB
        # row without rewriting project.json (Phase 9 / C4 dual-write rule).
        display = repo.model_copy(update={"name": db_row.name}) if db_row else repo
        items.append(_serialize_repo(display, repo_id, paths=paths))
    return JSONResponse(
        content={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )


@v1_router.get(
    "/{project_id}/repositories/{repo_id}",
    response_model=RepositoryItem,
)
async def get_repository_detail(
    project_id: int,
    repo_id: int,
    request: Request,
) -> JSONResponse:
    """Return a single repository. Auth fields are never echoed."""
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    registry = request.app.state.project_registry
    manager = ProjectManager(base_path, registry=registry)
    config = manager.get_project_info(row["name"])
    if config is None:
        raise NotFound(f"Project {project_id} not found")

    repo_repo = _make_repo_repo(row)
    db_row = repo_repo.get_by_id(repo_id)
    if db_row is None or db_row.deleted_at is not None:
        raise NotFound(f"Repository {repo_id} not found")

    config_repo = next((r for r in config.repositories if r.uuid == db_row.uuid), None)
    if config_repo is None:
        raise NotFound(f"Repository {repo_id} not found")

    # DB name is the source of truth (Phase 9 / C4 dual-write rule).
    display = config_repo.model_copy(update={"name": db_row.name})
    paths = ProjectPaths.from_registry_row(row)
    return JSONResponse(content=_serialize_repo(display, db_row.id, paths=paths))


def _parse_payload(payload: str | None) -> dict[str, Any]:
    """Parse a multipart-form ``payload`` JSON string into a dict."""
    if payload is None or payload == "":
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ApiValidationError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ApiValidationError("Payload must be a JSON object")
    return data


@v1_router.post("/{project_id}/repositories", status_code=201)
async def create_repository(
    project_id: int,
    request: Request,
    payload: str = Form(...),
    endpoint_file: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Create a new repository (multipart). Generates uuid server-side."""
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    project_name = row["name"]

    data = _parse_payload(payload)
    data.pop("uuid", None)

    try:
        repo = Repository.new(**data)
    except ValidationError as exc:
        raise ApiValidationError(str(exc)) from exc

    manager = ConfigManager(base_path)
    repo_repo = _make_repo_repo(row)
    with manager.locked_project_config(project_name):
        config = manager.load_project_config(project_name)
        if config is None:
            raise NotFound(f"Project {project_id} not found")
        if any(r.name == repo.name for r in config.repositories):
            raise ApiValidationError(
                f"Repository '{repo.name}' already exists in project"
            )
        repo_id = repo_repo.insert(uuid=repo.uuid, name=repo.name)
        config.repositories = [*config.repositories, repo]
        manager.save_project_config(project_name, config)

    if endpoint_file is not None and endpoint_file.filename:
        await _ingest_endpoint_file(row, repo, repo_id, endpoint_file)

    paths = ProjectPaths.from_registry_row(row)
    return JSONResponse(
        status_code=201, content=_serialize_repo(repo, repo_id, paths=paths)
    )


@v1_router.patch("/{project_id}/repositories/{repo_id}")
async def patch_repository(
    project_id: int,
    repo_id: int,
    request: Request,
    payload: str | None = Form(default=None),
    endpoint_file: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Partial update of a repository (multipart)."""
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    project_name = row["name"]

    repo_repo = _make_repo_repo(row)
    db_row = repo_repo.get_by_id(repo_id)
    if db_row is None or db_row.deleted_at is not None:
        raise NotFound(f"Repository {repo_id} not found")
    target_uuid = db_row.uuid

    data = _parse_payload(payload)
    data.pop("uuid", None)
    data.pop("id", None)

    manager = ConfigManager(base_path)
    with manager.locked_project_config(project_name):
        config = manager.load_project_config(project_name)
        if config is None:
            raise NotFound(f"Project {project_id} not found")
        idx = next(
            (i for i, r in enumerate(config.repositories) if r.uuid == target_uuid),
            None,
        )
        if idx is None:
            raise NotFound(f"Repository {repo_id} not found in project config")

        existing = config.repositories[idx]
        merged = existing.model_dump()
        merged.update(data)
        try:
            updated = Repository(**merged)
        except ValidationError as exc:
            raise ApiValidationError(str(exc)) from exc

        if updated.name != existing.name:
            repo_repo.rename(repo_id, updated.name)

        non_name_changed = existing.model_dump(exclude={"name"}) != updated.model_dump(
            exclude={"name"}
        )
        if non_name_changed:
            config.repositories = [
                *config.repositories[:idx],
                updated,
                *config.repositories[idx + 1 :],
            ]
            manager.save_project_config(project_name, config)

    if endpoint_file is not None and endpoint_file.filename:
        await _ingest_endpoint_file(row, updated, repo_id, endpoint_file)

    paths = ProjectPaths.from_registry_row(row)
    return JSONResponse(content=_serialize_repo(updated, repo_id, paths=paths))


@v1_router.delete("/{project_id}/repositories/{repo_id}", status_code=204)
async def delete_repository(
    project_id: int,
    repo_id: int,
    request: Request,
) -> Response:
    """Soft-delete a repository: mark deleted_at + drop from project.json."""
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    project_name = row["name"]

    repo_repo = _make_repo_repo(row)
    db_row = repo_repo.get_by_id(repo_id)
    if db_row is None or db_row.deleted_at is not None:
        raise NotFound(f"Repository {repo_id} not found")
    target_uuid = db_row.uuid

    manager = ConfigManager(base_path)
    with manager.locked_project_config(project_name):
        config = manager.load_project_config(project_name)
        if config is None:
            raise NotFound(f"Project {project_id} not found")
        config.repositories = [r for r in config.repositories if r.uuid != target_uuid]
        manager.save_project_config(project_name, config)
    repo_repo.soft_delete(repo_id)
    return Response(status_code=204)


@v1_router.patch(
    "/{project_id}/repositories/{repo_id}/auth",
    status_code=204,
)
async def patch_repository_auth(
    project_id: int,
    repo_id: int,
    request: Request,
    body: RepoAuthPatchRequest,
) -> Response:
    """Update the auth block on a repository (JSON). Auth is never echoed."""
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    project_name = row["name"]

    repo_repo = _make_repo_repo(row)
    db_row = repo_repo.get_by_id(repo_id)
    if db_row is None or db_row.deleted_at is not None:
        raise NotFound(f"Repository {repo_id} not found")
    target_uuid = db_row.uuid

    update = body.model_dump(exclude_none=True)
    manager = ConfigManager(base_path)
    with manager.locked_project_config(project_name):
        config = manager.load_project_config(project_name)
        if config is None:
            raise NotFound(f"Project {project_id} not found")
        idx = next(
            (i for i, r in enumerate(config.repositories) if r.uuid == target_uuid),
            None,
        )
        if idx is None:
            raise NotFound(f"Repository {repo_id} not found in project config")
        existing = config.repositories[idx]
        existing_auth = existing.auth.model_dump() if existing.auth else {}
        merged_auth = {**existing_auth, **update}
        try:
            from core.config.schemas.repository import RepoAuth

            new_auth = RepoAuth(**merged_auth)
            updated = existing.model_copy(update={"auth": new_auth})
            Repository(**updated.model_dump())
        except ValidationError as exc:
            raise ApiValidationError(str(exc)) from exc
        config.repositories = [
            *config.repositories[:idx],
            updated,
            *config.repositories[idx + 1 :],
        ]
        manager.save_project_config(project_name, config)
    return Response(status_code=204)


async def _ingest_endpoint_file(
    row: dict,
    repo: Repository,
    repo_id: int,
    endpoint_file: UploadFile,
) -> None:
    """Save the upload under user_uploads/ and ingest via UserFileProvider."""
    from application.url_inventory.ports import UrlProviderContext
    from application.url_inventory.providers.user_file import UserFileProvider
    from application.url_inventory.service import UrlInventoryService
    from infrastructure.store.repositories.url_findings import UrlFindingRepository

    paths = ProjectPaths.from_registry_row(row)
    upload_dir = paths.endpoints_dir / repo.uuid / "user_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / (endpoint_file.filename or "upload.json")
    dest.write_bytes(await endpoint_file.read())

    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    service = UrlInventoryService(UrlFindingRepository(factory))
    ctx = UrlProviderContext(
        repo=repo,
        repo_id=repo_id,
        base_path=str(paths.root.parent.parent),
        project_name=row["name"],
        run_id=None,
    )
    entries = list(UserFileProvider().provide(ctx, file_path=str(dest)))
    service.ingest_user_file(
        repo_id=repo_id,
        file_path=str(dest),
        entries=entries,
    )
