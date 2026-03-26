"""FastAPI application factory and uvicorn launcher for the web UI."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from application.rag.engine import RAGEngine
from infrastructure.store.connection import ConnectionFactory
from web.api.config import router as config_router
from web.api.findings import router as findings_router
from web.api.projects import router as projects_router

logger = logging.getLogger(__name__)


class _BearerTokenMiddleware(BaseHTTPMiddleware):
    """Require Authorization: Bearer <token> on /api/* routes only.

    Non-API paths (the SPA root, static assets) pass through unauthenticated
    so that the browser can load index.html and extract the token from the
    ``?token=`` query parameter before making any API calls.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.startswith("/api/"):
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

    app.include_router(config_router, prefix="/api/config")
    app.include_router(findings_router, prefix="/api/findings")
    app.include_router(projects_router, prefix="/api/projects")

    db_path = Path(base_path) / "projects" / project_name / "sqlite" / "findings.db"
    factory = ConnectionFactory(db_path)

    rag_engine: RAGEngine | None
    try:
        rag_engine = RAGEngine(project_name=project_name, base_path=base_path)
    except Exception as exc:
        logger.warning("RAGEngine init failed — Chroma sync will be disabled: %s", exc)
        rag_engine = None

    app.state.base_path = base_path
    app.state.project_name = project_name
    app.state.token = token
    app.state.connection_factory = factory
    app.state.rag_engine = rag_engine

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


def _attach_file_logging(base_path: str) -> None:
    """Attach a dated FileHandler to uvicorn loggers.

    Writes to ``<base_path>/logs/mm-dd-yy-server.log``.  The directory is
    created if it does not exist.
    """
    log_dir = Path(base_path) / "logs"
    log_dir.mkdir(exist_ok=True)
    log_filename = datetime.now().strftime("%m-%d-%y") + "-server.log"
    log_path = log_dir / log_filename

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
    )
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log_instance = logging.getLogger(logger_name)
        log_instance.addHandler(file_handler)
        log_instance.propagate = False


def create_server(
    base_path: str, project_name: str, port: int, token: str
) -> uvicorn.Server:
    """Create a uvicorn Server ready to be served in a daemon thread.

    Signal handling is disabled by replacing ``capture_signals`` with
    ``contextlib.nullcontext``.  Python only allows signal handlers to be
    installed on the main thread; without this the server would raise when
    started from a daemon thread.

    Call ``asyncio.run(server.serve())`` in the daemon thread to start it.
    Set ``server.should_exit = True`` to stop it gracefully.

    Args:
        base_path: Tally base directory.
        project_name: Active project name.
        port: TCP port to bind (localhost only).
        token: Per-session bearer token for request authentication.

    Returns:
        A configured ``uvicorn.Server`` instance (not yet started).
    """
    _attach_file_logging(base_path)
    app = create_app(base_path, project_name, token)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    # Disable signal handler installation — only allowed on the main thread.
    server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
    return server


def start(base_path: str, project_name: str, port: int, token: str) -> None:
    """Launch the web UI server (blocking).

    Thin wrapper around ``create_server()`` + ``asyncio.run()``.  Intended for
    use in a daemon thread.  Prefer ``create_server()`` when you need a handle
    to the server for graceful shutdown via ``server.should_exit = True``.
    """
    import asyncio

    server = create_server(base_path, project_name, port, token)
    asyncio.run(server.serve())
