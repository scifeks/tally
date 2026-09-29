"""CLI handler for MCP server commands."""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from core.security.credentials import get_encryption_key
from infrastructure.store.repositories.mcp_tokens import (
    McpTokenRepository,
)
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
    """Start the MCP server."""
    try:
        config = ConfigManager(str(base_path))
        mcp_cfg = config.global_config.mcp
        port = args.port if hasattr(args, "port") and args.port else mcp_cfg.port

        projects = project_registry.list_active()
        if not projects:
            logger.error(
                "No projects configured. "
                "Create a project before starting the MCP server."
            )
            return 1

        credentials_key_path = base_path / "mcp_credentials.key"
        if not credentials_key_path.exists():
            logger.error("No MCP tokens found. Run 'mcp token create <name>' first.")
            return 1
        encryption_key = get_encryption_key(credentials_key_path)

        registry_db_path = base_path / "tally.db"
        token_repo = McpTokenRepository(registry_db_path)
        tokens = token_repo.list_all()
        if not tokens:
            logger.error("No MCP tokens found. Run 'mcp token create <name>' first.")
            return 1

        logger.info(
            "MCP server starting on %s:%d",
            mcp_cfg.host,
            port,
        )
        start_mcp_server(
            port,
            project_registry,
            tool_registry,
            token_repo,
            encryption_key,
            base_path,
        )
        return 0
    except KeyboardInterrupt:
        logger.info("MCP server shut down by user")
        return 0
    except Exception as exc:
        logger.error("MCP server failed: %s", exc, exc_info=True)
        return 1
