"""FastAPI application factory and uvicorn launcher for the web UI."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.capabilities.service import CapabilitiesService
from application.project.registry_service import ProjectRegistryService
from application.runtime.dependency_service import RuntimeDependencyService
from application.scans.scans_service import ScansService
from infrastructure.events.bus import EventBus
from infrastructure.runtime.claude_probe import ClaudeCodeProbe
from infrastructure.store.project_registry import ProjectRegistryRepository
from infrastructure.system.installed_tools_probe import InstalledToolsProbe
from web.api._errors import install_error_handlers
from web.api._redact import install_redaction_middleware
from web.api.auth import router as auth_router
from web.api.chat import v1_router as chat_projects_v1_router
from web.api.config import router as config_router
from web.api.findings import v1_router as findings_v1_router
from web.api.locks import router as locks_router
from web.api.platform import platform_v1_router
from web.api.projects import v1_router as projects_v1_router
from web.api.reports import v1_router as reports_projects_v1_router
from web.api.scans import v1_router as scans_projects_v1_router
from web.api.tools import projects_tools_v1_router, runtime_v1_router, tools_v1_router
from web.api.triage import v1_router as triage_projects_v1_router
from web.api.url_list import url_list_v1_router
from web.auth.handshake import HandshakeRegistry
from web.auth.sessions import SessionStore
from web.middleware.access_log import AccessLogMiddleware
from web.middleware.csrf import CSRFMiddleware
from web.middleware.host_header import HostHeaderMiddleware
from web.middleware.origin import OriginCheckMiddleware
from web.middleware.security_headers import SecurityHeadersMiddleware
from web.middleware.session_auth import SessionAuthMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the streaming event-bus jobs; close them on shutdown."""
    bus = EventBus()
    app.state.event_bus = bus
    await bus.register_job("finding", "finding")
    await bus.register_job("scan", "scan")
    await bus.register_job("triage", "triage")
    await bus.register_job("report", "report")
    await bus.register_job("report_draft", "report_draft")
    await bus.register_job("chat", "chat")
    yield
    with contextlib.suppress(Exception):
        await bus.close_job("finding")
    with contextlib.suppress(Exception):
        await bus.close_job("scan")
    with contextlib.suppress(Exception):
        await bus.close_job("triage")
    with contextlib.suppress(Exception):
        await bus.close_job("report")
    with contextlib.suppress(Exception):
        await bus.close_job("report_draft")
    with contextlib.suppress(Exception):
        await bus.close_job("chat")


def create_app(
    base_path: str,
    handshake_token: str,
    *,
    port: int,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    The server is project-agnostic: every domain endpoint takes
    ``:project_id`` in the path and resolves it against the project
    registry per request. FindingKnowledgeBase instances are lazily
    built and cached per project.

    Args:
        base_path: Tally base directory (same as ``ConfigManager.base_path``).
        handshake_token: One-time token; SPA exchanges it for session cookies.
        port: Bound port — used by Host/Origin middleware allowlists.
        allowed_origins: CORS allow-list. Empty or None disables CORS entirely.

    Returns:
        Configured ``FastAPI`` instance.
    """
    app = FastAPI(title="Tally Web UI", lifespan=_lifespan)
    install_error_handlers(app)

    registry = HandshakeRegistry()
    registry.register(handshake_token)

    app.state.base_path = base_path
    app.state.handshake_registry = registry
    app.state.session_store = SessionStore()

    registry_repo = ProjectRegistryRepository(Path(base_path) / "tally.db")
    registry_repo.init_schema()
    project_registry = ProjectRegistryService(registry_repo)
    project_registry.sync(base_path)
    app.state.project_registry = project_registry

    ScansService.mark_stale_failed_for_all_projects(project_registry)

    app.state.knowledge_base_cache = {}

    app.state.installed_tools = InstalledToolsProbe()

    app.state.runtime_dependency_service = RuntimeDependencyService([ClaudeCodeProbe()])

    app.state.capabilities_service = CapabilitiesService(
        base_path=base_path,
        runtime_service=app.state.runtime_dependency_service,
    )

    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(config_router, prefix="/api/v1/config")
    app.include_router(findings_v1_router, prefix="/api/v1/projects")
    app.include_router(locks_router, prefix="/api/v1/projects")
    app.include_router(projects_v1_router, prefix="/api/v1/projects")
    app.include_router(tools_v1_router, prefix="/api/v1/tools")
    app.include_router(projects_tools_v1_router, prefix="/api/v1/projects")
    app.include_router(runtime_v1_router, prefix="/api/v1")
    app.include_router(platform_v1_router, prefix="/api/v1")
    app.include_router(scans_projects_v1_router, prefix="/api/v1/projects")
    app.include_router(triage_projects_v1_router, prefix="/api/v1/projects")
    app.include_router(reports_projects_v1_router, prefix="/api/v1/projects")
    app.include_router(chat_projects_v1_router, prefix="/api/v1/projects")
    app.include_router(url_list_v1_router, prefix="/api/v1/projects")

    # Middleware added in reverse execution order (Starlette LIFO).
    # Execution: SecurityHeaders → AccessLog → CORS → Host → Origin →
    #            SessionAuth → CSRF → Redaction → handler.
    # SecurityHeaders is the outermost wrapper so its headers attach to
    # every response — including 400/401/403 short-circuits from inner
    # middlewares.
    install_redaction_middleware(app)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SessionAuthMiddleware)
    app.add_middleware(
        OriginCheckMiddleware,
        port=port,
        extra_origins=allowed_origins or [],
    )
    app.add_middleware(HostHeaderMiddleware, port=port)

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

    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

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
    port: int,
    handshake_token: str,
    host: str = "127.0.0.1",
    allowed_origins: list[str] | None = None,
) -> uvicorn.Server:
    """Create a uvicorn Server ready to run in a daemon thread.

    Signal handling is disabled (``capture_signals`` replaced with
    ``contextlib.nullcontext``) so the server can start from a non-main thread.
    """
    _attach_file_logging(base_path)
    _attach_access_logging(base_path)
    app = create_app(
        base_path,
        handshake_token,
        port=port,
        allowed_origins=allowed_origins,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
    return server


def create_web_app(
    base_path: str,
    port: int,
    handshake_token: str,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    """Create the FastAPI application for direct ``uvicorn.run`` usage."""
    _attach_file_logging(base_path)
    _attach_access_logging(base_path)
    return create_app(
        base_path,
        handshake_token,
        port=port,
        allowed_origins=allowed_origins,
    )


def start(
    base_path: str,
    port: int,
    handshake_token: str,
    host: str = "127.0.0.1",
    allowed_origins: list[str] | None = None,
) -> None:
    """Launch the web UI server (blocking)."""
    import asyncio

    server = create_server(base_path, port, handshake_token, host, allowed_origins)
    asyncio.run(server.serve())
