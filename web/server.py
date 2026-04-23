"""FastAPI application factory and uvicorn launcher for the web UI."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from application.rag.engine import RAGEngine
from infrastructure.store.connection import ConnectionFactory
from web.api._errors import install_error_handlers
from web.api.auth import router as auth_router
from web.api.config import router as config_router
from web.api.findings import router as findings_router
from web.api.locks import router as locks_router
from web.api.projects import router as projects_router
from web.auth.handshake import HandshakeRegistry
from web.auth.sessions import SessionStore
from web.middleware.csrf import CSRFMiddleware
from web.middleware.host_header import HostHeaderMiddleware
from web.middleware.origin import OriginCheckMiddleware
from web.middleware.session_auth import SessionAuthMiddleware

logger = logging.getLogger(__name__)


def create_app(
    base_path: str,
    project_name: str,
    handshake_token: str,
    *,
    port: int,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        base_path: Tally base directory (same as ``ConfigManager.base_path``).
        project_name: Active project name.
        handshake_token: One-time token; SPA exchanges it for session cookies.
        port: Bound port — used by Host/Origin middleware allowlists.

    Returns:
        Configured ``FastAPI`` instance.
    """
    app = FastAPI(title="Tally Web UI")
    install_error_handlers(app)

    registry = HandshakeRegistry()
    registry.register(handshake_token)

    app.state.base_path = base_path
    app.state.project_name = project_name
    app.state.handshake_registry = registry
    app.state.session_store = SessionStore()

    # todo: This doesn't belong here
    db_path = Path(base_path) / "projects" / project_name / "sqlite" / "findings.db"
    app.state.connection_factory = ConnectionFactory(db_path)

    rag_engine: RAGEngine | None
    try:
        rag_engine = RAGEngine(project_name=project_name, base_path=base_path)
    except Exception as exc:
        logger.warning("RAGEngine init failed — Chroma sync will be disabled: %s", exc)
        rag_engine = None
    app.state.rag_engine = rag_engine

    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(config_router, prefix="/api/config")
    app.include_router(findings_router, prefix="/api/v1/findings")
    app.include_router(locks_router, prefix="/api/v1/projects")
    app.include_router(projects_router, prefix="/api/projects")

    # Middleware added in reverse execution order (Starlette LIFO).
    # Execution order: Host → Origin → SessionAuth → CSRF → route handler.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SessionAuthMiddleware)
    app.add_middleware(OriginCheckMiddleware, port=port)
    app.add_middleware(HostHeaderMiddleware, port=port)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        from fastapi.staticfiles import StaticFiles

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


# todo: Logging does not need to be duplicated and it is not the concern of the server.
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
    base_path: str,
    project_name: str,
    port: int,
    handshake_token: str,
) -> uvicorn.Server:
    """Create a uvicorn Server ready to run in a daemon thread.

    Signal handling is disabled (``capture_signals`` replaced with
    ``contextlib.nullcontext``) so the server can start from a non-main thread.

    Args:
        base_path: Tally base directory.
        project_name: Active project name.
        port: TCP port to bind (localhost only).
        handshake_token: One-time URL token; SPA exchanges it for session cookies.

    Returns:
        A configured ``uvicorn.Server`` instance (not yet started).
    """
    _attach_file_logging(base_path)
    app = create_app(base_path, project_name, handshake_token, port=port)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
    return server


def start(base_path: str, project_name: str, port: int, handshake_token: str) -> None:
    """Launch the web UI server (blocking).

    Thin wrapper around ``create_server()`` + ``asyncio.run()``.  Intended for
    use in a daemon thread.  Prefer ``create_server()`` when you need a handle
    to the server for graceful shutdown via ``server.should_exit = True``.
    """
    import asyncio

    server = create_server(base_path, project_name, port, handshake_token)
    asyncio.run(server.serve())
