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

from web.api._redact import redact_exempt

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
