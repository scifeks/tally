"""MCP server factory with SSE transport for Tally triage."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mcp.server import FastMCP

from application.mcp.service import McpTriageService
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import (
    FindingRepository,
)
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import (
    TriageBatchRepository,
)
from mcp_server.auth import validate_bearer_token

if TYPE_CHECKING:
    from application.ports.mcp_token_repository import (
        McpTokenRepositoryPort,
    )
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_mcp_server(
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    token_repo: McpTokenRepositoryPort,
    encryption_key: bytes,
) -> FastMCP:
    """Create the MCP server with triage tools."""
    server = FastMCP(
        name="Tally Triage",
        instructions=(
            "Tally triage tools: fetch_batch, submit_verdicts,"
            " skip_batch. Pass your bearer token as the"
            " auth_token parameter."
        ),
    )

    def _require_auth(auth_token: str) -> None:
        if not validate_bearer_token(
            f"Bearer {auth_token}",
            token_repo,
            encryption_key,
        ):
            raise PermissionError("Invalid or missing MCP token")

    def _get_service(
        project_name: str,
    ) -> McpTriageService:
        row = project_registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            raise ValueError(f"Project '{project_name}' not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        return McpTriageService(
            triage_repo=TriageBatchRepository(factory),
            finding_repo=FindingRepository(factory),
            run_repo=RunRepository(factory),
            tool_registry=tool_registry,
        )

    @server.tool()
    def fetch_batch(project: str, auth_token: str) -> dict[str, Any]:
        """Fetch the next triage batch for a project."""
        _require_auth(auth_token)
        service = _get_service(project)
        return service.fetch_batch(project)

    @server.tool()
    def submit_verdicts(
        project: str,
        batch_id: int,
        verdicts: list[dict[str, Any]],
        auth_token: str,
    ) -> dict[str, Any]:
        """Submit verdicts for a triage batch."""
        _require_auth(auth_token)
        service = _get_service(project)
        return service.submit_verdicts(batch_id, verdicts, project_name=project)

    @server.tool()
    def skip_batch(project: str, batch_id: int, auth_token: str) -> dict[str, str]:
        """Skip a triage batch without processing."""
        _require_auth(auth_token)
        service = _get_service(project)
        return service.skip_batch(batch_id)

    return server


def start_mcp_server(
    port: int,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    token_repo: McpTokenRepositoryPort,
    encryption_key: bytes,
) -> None:
    """Launch the MCP server with SSE transport (blocking)."""
    server = create_mcp_server(
        project_registry,
        tool_registry,
        token_repo,
        encryption_key,
    )
    logger.info(
        "Starting MCP server on port %d with SSE transport",
        port,
    )
    server.run(transport="sse")
