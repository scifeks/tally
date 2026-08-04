"""CLI handler for MCP server commands."""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from core.security.credentials import get_encryption_key
from infrastructure.store.repositories.mcp_tokens import McpTokenRepository
from mcp_server.server import start_mcp_server

if TYPE_CHECKING:
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def cmd_mcp_serve(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Start the MCP server with SSE transport.

    Args:
        args: Parsed CLI arguments with optional --port override.
        project_registry: Service for resolving projects.
        tool_registry: Registry of security tools.
        base_path: Base path for Tally (projects directory, config, etc).

    Returns:
        Exit code (0 on successful start, 1 on error).
    """
    try:
        config = ConfigManager(str(base_path))
        port = (
            args.port
            if hasattr(args, "port") and args.port
            else (config.global_config.mcp_port)
        )

        # Resolve global credentials
        credentials_key_path = (
            ProjectPaths(base_path).sqlite_dir / "mcp_credentials.key"
        )
        encryption_key = get_encryption_key(credentials_key_path)

        # Load token repository
        registry_db_path = base_path / "tally.db"
        token_repo = McpTokenRepository(registry_db_path)

        logger.info("MCP server starting on 127.0.0.1:%d with SSE transport", port)
        start_mcp_server(
            port,
            project_registry,
            tool_registry,
            token_repo,
            encryption_key,
        )
        return 0
    except KeyboardInterrupt:
        logger.info("MCP server shut down by user")
        return 0
    except Exception as exc:
        logger.error("MCP server failed: %s", exc, exc_info=True)
        return 1
