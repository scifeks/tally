"""Platform-level endpoints (health, etc.).

Hosts the unauthenticated ``GET /api/v1/health`` endpoint. The handler
probes the global project-registry SQLite to report DB reachability,
and reports the running package version via ``importlib.metadata``.
"""

from __future__ import annotations

import sqlite3
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from application.capabilities.service import CapabilitiesService
from web.api._redact import redact_exempt
from web.api.schemas import CapabilitiesResponse

platform_v1_router = APIRouter()


def _read_version() -> str:
    try:
        return version("tally")
    except PackageNotFoundError:
        return "0.0.0"


_VERSION = _read_version()


# Health response is fully reviewed; no field needs redaction.
@platform_v1_router.get("/health")
@redact_exempt
async def health(request: Request) -> JSONResponse:
    """Return platform liveness + DB reachability + build version."""
    registry = request.app.state.project_registry
    try:
        registry.ping()
    except sqlite3.Error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "db": "error",
                "version": _VERSION,
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "db": "ok",
            "version": _VERSION,
        },
    )


@platform_v1_router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(request: Request) -> CapabilitiesResponse:
    """Return SPA feature flags (chat / triage / report retention)."""
    service: CapabilitiesService = request.app.state.capabilities_service
    caps = service.compute()
    return CapabilitiesResponse(
        chat_enabled=caps.chat_enabled,
        triage_enabled=caps.triage_enabled,
        report_retention_enabled=caps.report_retention_enabled,
        max_report_history=caps.max_report_history,
    )
