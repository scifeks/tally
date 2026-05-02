"""URL list API endpoints.

Read-flavored endpoints over the ``url_findings`` table:

- ``GET /api/v1/projects/{project_id}/url-list/entries``: paginated rows.
- ``GET /api/v1/projects/{project_id}/url-list/export``: csv/json/txt
  download.
- ``POST /api/v1/projects/{project_id}/url-list/regenerate``: rebuild
  ``merged_urls.txt`` + ``merged_oas3.json`` on disk for every active
  repo.
"""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from application.url_inventory.url_list_service import (
    ProjectNotFound,
    UrlListService,
)
from core.project_paths import ProjectPaths
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool
from web.api._errors import NotFound
from web.api._errors import ValidationError as ApiValidationError
from web.api._project_resolver import _resolve_project
from web.api._redact import redact_exempt
from web.api.schemas import UrlListFilterOptionsResponse

url_list_v1_router = APIRouter()


def _service(request: Request, project_id: int) -> UrlListService:
    """Build a UrlListService for *project_id* or raise 404."""
    try:
        return UrlListService.for_project(
            request.app.state.project_registry, project_id
        )
    except ProjectNotFound as exc:
        raise NotFound(f"project {project_id} not found") from exc


def _row_to_dict(
    f: UrlFinding,
    project_id: int,
    repo_name_by_id: dict[int, str],
) -> dict:
    return {
        "id": f.id,
        "project_id": project_id,
        "repo_id": f.repo_id,
        "repo_name": repo_name_by_id.get(f.repo_id, ""),
        "source": str(f.source),
        "tool": str(f.tool) if f.tool is not None else None,
        "run_id": f.run_id,
        "method": f.method,
        "protocol": f.protocol,
        "host": f.host,
        "port": f.port,
        "path": f.path,
        "file_path": f.file_path,
        "meta": f.meta,
        "created_at": f.created_at,
    }


def _parse_source(value: str | None) -> UrlSource | None:
    if value is None:
        return None
    try:
        return UrlSource(value)
    except ValueError as exc:
        raise ApiValidationError(f"Invalid source: {value}") from exc


def _parse_tool(value: str | None) -> UrlTool | None:
    if value is None:
        return None
    try:
        return UrlTool(value)
    except ValueError as exc:
        raise ApiValidationError(f"Invalid tool: {value}") from exc


@url_list_v1_router.get("/{project_id}/url-list/entries")
async def list_url_entries(
    project_id: int,
    request: Request,
    repo_id: list[int] | None = Query(default=None),
    source: str | None = Query(default=None),
    tool: str | None = Query(default=None),
    method: list[str] | None = Query(default=None),
    protocol: list[str] | None = Query(default=None),
    host: list[str] | None = Query(default=None),
    port: list[int] | None = Query(default=None),
    path: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: str = Query(default="host"),
    order: str = Query(default="asc"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> JSONResponse:
    service = _service(request, project_id)
    rows, total = service.url_repo.list_paginated(
        repo_id=repo_id,
        source=_parse_source(source),
        tool=_parse_tool(tool),
        method=method,
        protocol=protocol,
        host=host,
        port=port,
        path=path,
        search=search,
        sort=sort,
        order=order,
        offset=offset,
        limit=limit,
    )
    repo_name_by_id = service.repo_name_lookup()
    items = [_row_to_dict(r, project_id, repo_name_by_id) for r in rows]
    return JSONResponse(
        content={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )


@url_list_v1_router.get(
    "/{project_id}/url-list/filter-options",
    response_model=UrlListFilterOptionsResponse,
)
async def get_url_list_filter_options(
    project_id: int,
    request: Request,
    repo_id: list[int] | None = Query(default=None),
    source: str | None = Query(default=None),
    tool: str | None = Query(default=None),
    method: list[str] | None = Query(default=None),
    protocol: list[str] | None = Query(default=None),
    host: list[str] | None = Query(default=None),
    port: list[int] | None = Query(default=None),
    path: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
) -> UrlListFilterOptionsResponse:
    """Per-dimension filter options under the active filter set.

    Mirrors the filter query params of ``GET /url-list/entries``. Each
    dimension's counts apply every active filter (strict semantics) and
    zero-count options are omitted. Powers the URL Lists page filter
    dropdowns.
    """
    service = _service(request, project_id)
    filters: dict = {
        "repo_id": repo_id,
        "source": _parse_source(source),
        "tool": _parse_tool(tool),
        "method": method,
        "protocol": protocol,
        "host": host,
        "port": port,
        "path": path,
        "search": search,
    }
    data = service.url_repo.filter_options(filters)
    return UrlListFilterOptionsResponse(**data)


@url_list_v1_router.get("/{project_id}/url-list/export")
@redact_exempt
async def export_url_list(
    project_id: int,
    request: Request,
    format: str = Query(default="json"),
) -> Response:
    if format not in ("json", "csv", "txt"):
        raise ApiValidationError(f"Unsupported format: {format}")

    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    rows, _ = service.url_repo.list_paginated(offset=0, limit=10_000)
    repo_name_by_id = service.repo_name_lookup()

    project_name = row.name
    filename = f"url-list-{project_name}.{format}"

    if format == "json":
        body = json.dumps(
            [_row_to_dict(r, project_id, repo_name_by_id) for r in rows],
            indent=2,
        )
        media = "application/json"
    elif format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "repo_id",
                "repo_name",
                "source",
                "tool",
                "method",
                "protocol",
                "host",
                "port",
                "path",
                "file_path",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.id,
                    r.repo_id,
                    repo_name_by_id.get(r.repo_id, ""),
                    str(r.source),
                    str(r.tool) if r.tool is not None else "",
                    r.method,
                    r.protocol,
                    r.host,
                    r.port,
                    r.path,
                    r.file_path or "",
                ]
            )
        body = buf.getvalue()
        media = "text/csv"
    else:  # txt
        body = "\n".join(f"{r.protocol}://{r.host}:{r.port}{r.path}" for r in rows)
        media = "text/plain"

    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@url_list_v1_router.post("/{project_id}/url-list/regenerate")
async def regenerate_url_list(
    project_id: int,
    request: Request,
) -> JSONResponse:
    """Rebuild merged_urls.txt and merged_oas3.json for every active repo."""
    from application.project.repositories_service import ProjectRepositoriesService

    row = _resolve_project(request, project_id)
    service = _service(request, project_id)
    paths = ProjectPaths.from_registry_row(row)

    repo_service = ProjectRepositoriesService.build(
        request.app.state.project_registry,
        request.app.state.base_path,
    )
    active_repos: list[tuple[int, str]] = [
        (r.id, str(r.id))
        for r in repo_service.list_active(project_id)
        if r.id is not None
    ]

    rebuilt = service.inventory.regenerate_artifacts_for_project(
        project_paths=paths,
        active_repos=active_repos,
    )
    regenerated = [
        {"repo_id": repo_id, "seeds_path": seeds_path, "oas3_path": oas3_path}
        for repo_id, seeds_path, oas3_path in rebuilt
    ]
    return JSONResponse(content={"regenerated": regenerated})
