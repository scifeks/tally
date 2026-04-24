"""FastAPI application factory and uvicorn launcher for the web UI."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.rag.engine import RAGEngine
from infrastructure.store.connection import ConnectionFactory
from web.api._errors import install_error_handlers
from web.api._redact import install_redaction_middleware
from web.api.auth import router as auth_router
from web.api.config import router as config_router
from web.api.findings import router as findings_router
from web.api.locks import router as locks_router
from web.api.projects import router as projects_router
from web.api.projects import v1_router as projects_v1_router
from web.auth.handshake import HandshakeRegistry
from web.auth.sessions import SessionStore
from web.middleware.access_log import AccessLogMiddleware
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
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        base_path: Tally base directory (same as ``ConfigManager.base_path``).
        project_name: Active project name.
        handshake_token: One-time token; SPA exchanges it for session cookies.
        port: Bound port — used by Host/Origin middleware allowlists.
        allowed_origins: CORS allow-list. Empty or None disables CORS entirely.

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
    app.include_router(projects_v1_router, prefix="/api/v1/projects")

    # Middleware added in reverse execution order (Starlette LIFO).
    # Execution: AccessLog → CORS → Host → Origin → SessionAuth → CSRF
    #            → Redaction → handler.
    install_redaction_middleware(app)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SessionAuthMiddleware)
    app.add_middleware(
        OriginCheckMiddleware,
        port=port,
        extra_origins=allowed_origins or [],
    )
    app.add_middleware(HostHeaderMiddleware, port=port)

    # CORS dev-only escape hatch for the Vite dev server.
    # Production posture: same-origin only (SPA served from web/static/).
    # Never allow "*" — explicit literal origins from config only.
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
            expose_headers=[],
            max_age=600,
        )
        logger.info("CORS allow-list installed for origins: %s", allowed_origins)

    # Outermost: access log wraps every other layer so latency covers the
    # full request and CORS preflight rejections are still logged.
    app.add_middleware(AccessLogMiddleware)

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


# todo: Add cross-midnight rollover, rquest-ID inner layer correlation
#  (context var), retention policy
# todo: Add a concept of log/run levels for debug vs normal logging
# todo: Turn off logging by default
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


def _attach_access_logging(base_path: str) -> None:
    """Attach a dated FileHandler to the access logger.

    Writes one JSON record per request to ``<base_path>/logs/web-YYYY-MM-DD.log``.
    The ``tally.web.access`` logger is isolated (``propagate=False``) so its
    records do not duplicate into uvicorn or root handlers.
    """
    log_dir = Path(base_path) / "logs"
    log_dir.mkdir(exist_ok=True)
    log_filename = "web-" + datetime.now().strftime("%Y-%m-%d") + ".log"
    log_path = log_dir / log_filename

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    access_logger = logging.getLogger("tally.web.access")
    access_logger.addHandler(file_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False


def create_server(
    base_path: str,
    project_name: str,
    port: int,
    handshake_token: str,
    host: str = "127.0.0.1",
    allowed_origins: list[str] | None = None,
) -> uvicorn.Server:
    """Create a uvicorn Server ready to run in a daemon thread.

    Signal handling is disabled (``capture_signals`` replaced with
    ``contextlib.nullcontext``) so the server can start from a non-main thread.

    Args:
        base_path: Tally base directory.
        project_name: Active project name.
        port: TCP port to bind.
        handshake_token: One-time URL token; SPA exchanges it for session cookies.
        host: Bind host (default ``"127.0.0.1"``).
        allowed_origins: CORS allow-list passed to ``create_app``.

    Returns:
        A configured ``uvicorn.Server`` instance (not yet started).
    """
    _attach_file_logging(base_path)
    _attach_access_logging(base_path)
    app = create_app(
        base_path,
        project_name,
        handshake_token,
        port=port,
        allowed_origins=allowed_origins,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
    return server


def start(
    base_path: str,
    project_name: str,
    port: int,
    handshake_token: str,
    host: str = "127.0.0.1",
    allowed_origins: list[str] | None = None,
) -> None:
    """Launch the web UI server (blocking).

    Thin wrapper around ``create_server()`` + ``asyncio.run()``.  Intended for
    use in a daemon thread.  Prefer ``create_server()`` when you need a handle
    to the server for graceful shutdown via ``server.should_exit = True``.
    """
    import asyncio

    server = create_server(
        base_path, project_name, port, handshake_token, host, allowed_origins
    )
    asyncio.run(server.serve())
