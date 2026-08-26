"""Burp scan endpoint: trigger a Burp crawl-and-audit scan."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request

from application.project.repositories_service import (
    ProjectRepositoriesService,
)
from core.project_paths import ProjectPaths
from factories.persistence import (
    create_finding_repo,
    create_repo_repo,
    create_scan_repos,
    create_url_finding_repo,
)
from factories.scanning import get_scan_service
from web.adapters.event_bus_scan_sink import EventBusScanSink
from web.adapters.no_approval_prompt import (
    NoApprovalPromptAdapter,
)
from web.api._errors import JobBusyError, NotFound, ValidationError
from web.api._project_resolver import _resolve_project
from web.api._scan_run_summary import scan_run_to_summary
from web.api.schemas import BurpScanStartRequest, ScanRunSummary

logger = logging.getLogger("tally.web.burp_scan")

v1_router = APIRouter()


def _collect_base_urls(
    project_registry,
    base_path: str,
    project_id: int,
) -> list[str]:
    repos_service = ProjectRepositoriesService.build(project_registry, base_path)
    urls: list[str] = []
    for repo in repos_service.list_active(project_id):
        for svc in repo.services:
            urls.extend(svc.base_urls)
    return urls


@v1_router.post(
    "/{project_id}/burp-scan",
    response_model=ScanRunSummary,
    status_code=202,
)
async def start_burp_scan(
    project_id: int,
    request: Request,
    body: BurpScanStartRequest,
) -> ScanRunSummary:
    """Start a Burp crawl-and-audit scan for a project."""
    row = _resolve_project(request, project_id)
    base_path: str = request.app.state.base_path

    urls = _collect_base_urls(
        request.app.state.project_registry,
        base_path,
        project_id,
    )
    if not urls:
        raise ValidationError(
            "No base URLs configured",
            details={
                "fields": [
                    {
                        "field": "base_urls",
                        "issue": (
                            "No base URLs found in project"
                            " repositories. Configure base"
                            " URLs on at least one"
                            " repository service."
                        ),
                    }
                ]
            },
        )

    from core.config.manager import ConfigManager

    cfg = ConfigManager(base_path)
    if cfg.global_config.burp is None:
        raise ValidationError(
            "Burp not configured",
            details={
                "fields": [
                    {
                        "field": "burp",
                        "issue": (
                            "No Burp configuration found"
                            " in config/global.json."
                            " Add a burp section with"
                            " base_url."
                        ),
                    }
                ]
            },
        )

    paths = ProjectPaths.from_registry_row(row)
    run_repo, chat_repo, profiles_repo, _ = create_scan_repos(paths.findings_db)
    finding_repo = create_finding_repo(paths.findings_db)
    repo_repo = create_repo_repo(paths.findings_db)
    url_finding_repo = create_url_finding_repo(paths.findings_db)

    sink = EventBusScanSink(request.app.state.event_bus)

    from application.locking import JobBusy

    try:
        handle = await asyncio.to_thread(
            get_scan_service().start_scan,
            project_id=project_id,
            project_name=row.name,
            base_path=base_path,
            tool_registry=request.app.state.tool_registry,
            run_repo=run_repo,
            chat_session_repo=chat_repo,
            profiles_repo=profiles_repo,
            finding_repo=finding_repo,
            repo_repo=repo_repo,
            url_finding_repo=url_finding_repo,
            prompt=NoApprovalPromptAdapter(),
            event_sink=sink,
            burp_urls=urls,
            burp_config_name=body.configName,
            burp_timeout=body.timeout,
        )
    except JobBusy as exc:
        raise JobBusyError(
            "scan",
            exc.current_holder,
        ) from exc

    fresh = await asyncio.to_thread(run_repo.get, handle.run_id)
    if fresh is None:
        raise NotFound(f"scan run {handle.run_id} not found")
    return scan_run_to_summary(fresh)
