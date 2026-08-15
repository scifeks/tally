"""MCP server factory with SSE transport for Tally triage and ingest."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from application.mcp.ingest_service import (
    McpIngestService,
    list_active_projects,
)
from application.mcp.service import McpTriageService
from application.rag.finding_indexer import FindingIndexer
from application.rag.knowledge_base_cache import (
    get_or_build_knowledge_base,
)
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
    from application.ports.run_repository import RunRepositoryPort
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
    base_path: str | Path,
) -> FastMCP:
    """Create the MCP server with triage and ingest tools."""
    server = FastMCP(
        name="Tally MCP",
        instructions=(
            "Tally MCP tools: fetch_batch, submit_verdicts,"
            " skip_batch, list_projects, create_scan_run,"
            " submit_finding, get_duplicate_candidates,"
            " resolve_duplicates, end_scan. Pass your bearer"
            " token as the auth_token parameter."
        ),
    )

    # KB cache for ingest service
    kb_cache: dict[str, Any] = {}
    base_path_obj = Path(base_path) if isinstance(base_path, str) else base_path

    def _require_auth(auth_token: str) -> None:
        if not validate_bearer_token(
            f"Bearer {auth_token}",
            token_repo,
            encryption_key,
        ):
            raise PermissionError("Invalid or missing MCP token")

    def _run_repo_factory(db_path: str) -> RunRepositoryPort:
        """Create a RunRepository from a db_path string."""
        conn_factory = ConnectionFactory(Path(db_path))
        conn_factory.init_schema()
        return RunRepository(conn_factory)

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

    def _get_ingest_service(project_name: str) -> McpIngestService:
        """Create an ingest service for a project with KB and indexer."""
        row = project_registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            raise ValueError(f"Project '{project_name}' not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        conn_factory = ConnectionFactory(paths.findings_db)
        conn_factory.init_schema()
        finding_repo = FindingRepository(conn_factory)
        run_repo = RunRepository(conn_factory)
        indexer = FindingIndexer(finding_repo=finding_repo)
        kb = get_or_build_knowledge_base(kb_cache, project_name, str(base_path_obj))
        return McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
            indexer=indexer,
            knowledge_base=kb,
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

    @server.tool()
    def list_projects(auth_token: str) -> list[dict[str, Any]]:
        """Enumerate every active project with its latest run id."""
        _require_auth(auth_token)
        return list_active_projects(project_registry, _run_repo_factory)

    @server.tool()
    def create_scan_run(
        project: str,
        project_id: int,
        repo_ids: list[str],
        auth_token: str,
    ) -> dict[str, int]:
        """Open a new scan_run for an external Claude Code scan."""
        _require_auth(auth_token)
        service = _get_ingest_service(project)
        return service.create_scan_run(project_id, repo_ids)

    @server.tool()
    def submit_finding(
        project: str,
        project_id: int,
        repo_id: int,
        run_id: int,
        finding: dict[str, Any],
        auth_token: str,
    ) -> dict[str, Any]:
        """Submit a single finding under an MCP scan_run."""
        _require_auth(auth_token)
        service = _get_ingest_service(project)
        return service.submit_finding(run_id, finding)

    @server.tool()
    def get_duplicate_candidates(
        project: str,
        run_id: int,
        auth_token: str,
    ) -> dict[str, Any]:
        """Return candidate duplicate groups for a scan run."""
        _require_auth(auth_token)
        service = _get_ingest_service(project)
        return service.get_duplicate_candidates(run_id)

    @server.tool()
    def resolve_duplicates(
        project: str,
        run_id: int,
        survivor_id: int,
        removed_ids: list[int],
        auth_token: str,
    ) -> dict[str, Any]:
        """Mark removed findings as duplicates of a survivor."""
        _require_auth(auth_token)
        service = _get_ingest_service(project)
        return service.resolve_duplicates(run_id, survivor_id, removed_ids)

    @server.tool()
    def end_scan(
        project: str,
        project_id: int,
        run_id: int,
        auth_token: str,
    ) -> dict[str, str]:
        """Mark a scan run as finished."""
        _require_auth(auth_token)
        service = _get_ingest_service(project)
        return service.end_scan(project_id, run_id)

    return server


def start_mcp_server(
    port: int,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    token_repo: McpTokenRepositoryPort,
    encryption_key: bytes,
    base_path: str | Path,
) -> None:
    """Launch the MCP server with SSE transport (blocking)."""
    server = create_mcp_server(
        project_registry,
        tool_registry,
        token_repo,
        encryption_key,
        base_path,
    )
    logger.info(
        "Starting MCP server on port %d with SSE transport",
        port,
    )
    server.run(transport="sse")
