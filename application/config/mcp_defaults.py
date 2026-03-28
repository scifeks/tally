"""Load MCP configuration via the application layer."""

from core.config.manager import ConfigManager
from core.config.schemas.global_config import (
    MCP_BATCH_SIZE_DEFAULT,
    MCP_BATCH_TIMEOUT_SECONDS_DEFAULT,
    MCP_SESSION_TIMEOUT_SECONDS_DEFAULT,
)


def load_mcp_defaults(app_root: str) -> tuple[int, int, int]:
    """Return (max_batch_size, batch_timeout_seconds, session_timeout_seconds).

    Falls back to schema defaults when no config file is found.
    """
    try:
        cfg = ConfigManager(app_root).global_config
        return (
            cfg.mcp_batch_size,
            cfg.mcp_batch_timeout_seconds,
            cfg.mcp_session_timeout_seconds,
        )
    except FileNotFoundError:
        return (
            MCP_BATCH_SIZE_DEFAULT,
            MCP_BATCH_TIMEOUT_SECONDS_DEFAULT,
            MCP_SESSION_TIMEOUT_SECONDS_DEFAULT,
        )
