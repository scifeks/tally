"""FastAPI application factory and uvicorn launcher for the web UI."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from infrastructure.store.connection import ConnectionFactory
from web.api.findings import router as findings_router
from web.api.projects import router as projects_router

logger = logging.getLogger(__name__)


class _BearerTokenMiddleware(BaseHTTPMiddleware):
    """Reject any request missing a valid Authorization: Bearer <token> header."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self._token}":
            return Response(
                content='{"detail": "Unauthorized"}',
                status_code=401,
                media_type="application/json",
            )
        return await call_next(request)


def create_app(base_path: str, project_name: str, token: str) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        base_path: Tally base directory (same as ``ConfigManager.base_path``).
        project_name: Active project name.
        token: Per-session bearer token for request authentication.

    Returns:
        Configured ``FastAPI`` instance.
    """
    app = FastAPI(title="Tally Web UI")

    app.add_middleware(_BearerTokenMiddleware, token=token)

    app.include_router(findings_router, prefix="/api/findings")
    app.include_router(projects_router, prefix="/api/projects")

    db_path = Path(base_path) / "projects" / project_name / "sqlite" / "findings.db"
    factory = ConnectionFactory(db_path)

    app.state.base_path = base_path
    app.state.project_name = project_name
    app.state.token = token
    app.state.connection_factory = factory

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
    else:
        logger.warning(
            "web/static/ not found — static file mount skipped. "
            "Run the frontend build step to enable the Vue SPA."
        )

    return app


def start(base_path: str, project_name: str, port: int, token: str) -> None:
    """Launch the web UI server (blocking).

    Intended to be called from a daemon thread by the REPL.  Binds to
    localhost only and never returns until the server shuts down.

    Args:
        base_path: Tally base directory.
        project_name: Active project name.
        port: TCP port to bind.
        token: Per-session bearer token for request authentication.
    """
    app = create_app(base_path, project_name, token)
    uvicorn.run(app, host="127.0.0.1", port=port)
