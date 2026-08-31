"""MCP server management endpoints."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Request

from application.mcp.lifecycle import (
    start_mcp_server_managed,
    stop_mcp_server,
)
from application.mcp.registry import get_mcp_server_registry
from application.triage.batch_creator import create_triage_batches
from core.config import ConfigManager
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository
from web.api._errors import NotFound
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    McpServeStatusResponse,
    McpServeStopResponse,
    McpTriageStartResponse,
)

logger = logging.getLogger("tally.web.mcp_serve")

project_router = APIRouter()
global_router = APIRouter()


@project_router.post(
    "/{project_id}/mcp/triage/start",
    response_model=McpTriageStartResponse,
    status_code=202,
)
async def start_mcp_triage(
    project_id: int,
    request: Request,
) -> McpTriageStartResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path

    cfg = ConfigManager(base_path).global_config
    mcp_cfg = cfg.mcp

    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    run_repo = RunRepository(factory)
    triage_repo = TriageBatchRepository(factory)

    run_id = run_repo.latest_run_id()
    if run_id is None:
        raise NotFound("No scan runs for this project")

    tool_registry = request.app.state.tool_registry
    batches = create_triage_batches(
        run_id=run_id,
        triage_repo=triage_repo,
        tool_registry=tool_registry,
        max_findings_per_batch=4,
    )

    total_findings = sum(count for _, count in batches)

    registry = get_mcp_server_registry()
    if not registry.is_active():
        start_mcp_server_managed(
            port=mcp_cfg.port,
            host=mcp_cfg.host.replace("http://", ""),
            project_registry=request.app.state.project_registry,
            tool_registry=tool_registry,
            token_repo=request.app.state.token_repo,
            encryption_key=request.app.state.encryption_key,
            base_path=base_path,
            source="web",
            event_publisher=request.app.state.event_bus,
        )

    token_repo = request.app.state.token_repo
    tokens = token_repo.get_all_encrypted()
    if not tokens:
        from core.security.credentials import encrypt_value

        raw = secrets.token_urlsafe(32)
        encrypted = encrypt_value(raw, request.app.state.encryption_key)
        token_repo.create("auto-web", encrypted)
        token_value = raw
    else:
        token_value = "<use existing token>"

    handle = registry.get()
    return McpTriageStartResponse(
        host=handle.host if handle else mcp_cfg.host,
        port=handle.port if handle else mcp_cfg.port,
        token=token_value,
        batchCount=len(batches),
        totalFindings=total_findings,
    )


@global_router.post(
    "/mcp/serve/stop",
    response_model=McpServeStopResponse,
)
async def stop_serve(
    request: Request,
) -> McpServeStopResponse:
    stopped = stop_mcp_server()
    if not stopped:
        raise NotFound("No active MCP server")
    return McpServeStopResponse(status="stopped")


@global_router.get(
    "/mcp/serve/status",
    response_model=McpServeStatusResponse,
)
async def serve_status(
    request: Request,
) -> McpServeStatusResponse:
    handle = get_mcp_server_registry().get()
    if handle is None:
        return McpServeStatusResponse(active=False)
    return McpServeStatusResponse(
        active=True,
        host=handle.host,
        port=handle.port,
        source=handle.source,
    )
