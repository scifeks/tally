"""Managed MCP server start/stop with uvicorn shutdown."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from application.mcp.registry import (
    McpServerHandle,
    get_mcp_server_registry,
)

if TYPE_CHECKING:
    from application.ports.event_publisher import (
        EventPublisherPort,
    )
    from application.ports.mcp_token_repository import (
        McpTokenRepositoryPort,
    )
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.tools.registry import ToolRegistry

_log = logging.getLogger(__name__)


def start_mcp_server_managed(
    *,
    port: int,
    host: str = "127.0.0.1",
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    token_repo: McpTokenRepositoryPort,
    encryption_key: bytes,
    base_path: str | Path,
    source: str,
    event_publisher: EventPublisherPort | None = None,
) -> McpServerHandle:
    """Start the MCP server in a daemon thread."""
    from mcp_server.server import create_mcp_server

    registry = get_mcp_server_registry()
    active_handle = registry.get()
    if active_handle is not None:
        raise RuntimeError(f"MCP server already running on port {active_handle.port}")

    mcp = create_mcp_server(
        project_registry=project_registry,
        tool_registry=tool_registry,
        base_path=base_path,
        event_publisher=event_publisher,
    )
    from mcp_server.auth import BearerTokenMiddleware

    app = mcp.streamable_http_app()
    app = BearerTokenMiddleware(app, token_repo, encryption_key)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    def _worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        except Exception:
            _log.exception("MCP server crashed")
        finally:
            loop.close()
            registry.unregister()

    thread = threading.Thread(
        target=_worker,
        name="mcp-server",
        daemon=True,
    )

    handle = McpServerHandle(
        host=host,
        port=port,
        source=source,
        server=server,
        thread=thread,
    )
    registry.register(handle)
    thread.start()
    _log.info(
        "MCP server started on %s:%d (source=%s)",
        host,
        port,
        source,
    )
    return handle


def stop_mcp_server() -> bool:
    """Stop the running MCP server. Returns True if stopped."""
    registry = get_mcp_server_registry()
    handle = registry.get()
    if handle is None:
        return False
    handle.server.should_exit = True
    return True
