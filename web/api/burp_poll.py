"""Burp Organizer poll endpoints: start, cancel, status."""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Request

from application.locking.cancellation import CancellationToken
from application.mcp.ingest_service import McpIngestService
from application.tools.burp.note_enrichment import NoteEnrichment
from application.tools.burp.organizer_poller import OrganizerPoller
from application.tools.burp.poll_registry import (
    get_burp_poll_registry,
)
from core.config import ConfigManager
from core.project_paths import ProjectPaths
from factories.llm import create_llm_provider
from factories.persistence import create_finding_repo
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.organizer_state import (
    OrganizerStateRepository,
)
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.tools.burp.mcp_client import BurpMcpClient
from web.adapters.event_bus_finding_sink import (
    EventBusFindingSink,
)
from web.api._errors import Conflict, NotFound
from web.api._errors import (
    ValidationError as ApiValidationError,
)
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    BurpPollCancelResponse,
    BurpPollStartResponse,
    BurpPollStatusResponse,
)

logger = logging.getLogger("tally.web.burp_poll")

v1_router = APIRouter()


def _burp_config(base_path: str):
    return ConfigManager(base_path).global_config.burp


@v1_router.post(
    "/{project_id}/burp/poll",
    response_model=BurpPollStartResponse,
    status_code=202,
)
async def start_poll(
    project_id: int,
    request: Request,
) -> BurpPollStartResponse:
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path

    burp_cfg = _burp_config(base_path)
    if not burp_cfg or not burp_cfg.mcp_url:
        raise ApiValidationError(
            "Burp MCP URL not configured",
            details={"field": "burp.mcp_url"},
        )

    registry = get_burp_poll_registry()
    if registry.get_for_project(project_id) is not None:
        raise Conflict(
            "Burp poll already active for this project",
            code="BURP_POLL_ALREADY_RUNNING",
        )

    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    run_repo = RunRepository(factory)
    finding_repo = create_finding_repo(paths.findings_db)
    state_repo = OrganizerStateRepository(factory)
    fetcher = BurpMcpClient(burp_cfg.mcp_url)
    ingest = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)

    note_enrichment: NoteEnrichment | None = None
    try:
        provider = create_llm_provider("enrichment", base_path)
        note_enrichment = NoteEnrichment(provider)
    except Exception:
        logger.debug("LLM enrichment unavailable for poll")

    event_sink = EventBusFindingSink(request.app.state.event_bus)

    poller = OrganizerPoller(
        fetcher=fetcher,
        state_repo=state_repo,
        ingest_service=ingest,
        project_id=project_id,
        poll_interval=float(burp_cfg.poll_interval_seconds),
        note_enrichment=note_enrichment,
        finding_repo=finding_repo,
        event_sink=event_sink,
    )

    cancel_token = CancellationToken()
    registry.register(
        project_id=project_id,
        cancel_token=cancel_token,
    )

    def _worker() -> None:
        try:
            poller.run(cancel_token)
        except Exception:
            logger.exception("Burp poll worker crashed")
        finally:
            registry.unregister(project_id)

    thread = threading.Thread(
        target=_worker,
        name=f"burp-poll-{project_id}",
        daemon=True,
    )
    thread.start()

    return BurpPollStartResponse(project_id=project_id, status="polling")


@v1_router.post(
    "/{project_id}/burp/poll/cancel",
    response_model=BurpPollCancelResponse,
    status_code=202,
)
async def cancel_poll(
    project_id: int,
    request: Request,
) -> BurpPollCancelResponse:
    _resolve_project(request, project_id)
    registry = get_burp_poll_registry()
    handle = registry.get_for_project(project_id)
    if handle is None:
        raise NotFound("no active Burp poll for this project")
    handle.cancel_token.set()
    return BurpPollCancelResponse(project_id=project_id, status="stopping")


@v1_router.get(
    "/{project_id}/burp/poll/status",
    response_model=BurpPollStatusResponse,
)
async def poll_status(
    project_id: int,
    request: Request,
) -> BurpPollStatusResponse:
    _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path
    burp_cfg = _burp_config(base_path)
    configured = bool(burp_cfg and burp_cfg.mcp_url)
    registry = get_burp_poll_registry()
    active = registry.get_for_project(project_id) is not None
    return BurpPollStatusResponse(
        project_id=project_id,
        configured=configured,
        active=active,
    )
