"""WebUiRunner port: launch the embedded web UI dev server.

Owns FastAPI app construction, uvicorn lifecycle, Vite dev-server spawn,
browser launch, and .env.local seed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


@runtime_checkable
class WebUiRunnerPort(Protocol):
    """Start the embedded web UI dev server. Blocks until the user stops it."""

    def serve(
        self,
        *,
        base_path: str,
        host: str,
        api_port: int,
        vite_port: int,
        allowed_origins: list[str],
        project_registry: ProjectRegistryService,
        tool_registry: ToolRegistry,
    ) -> None: ...
