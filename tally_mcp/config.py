from pathlib import Path

from core.config.manager import ConfigManager
from core.config.schemas.global_config import (
    MCP_BATCH_SIZE_DEFAULT,
    MCP_BATCH_TIMEOUT_SECONDS_DEFAULT,
    MCP_SESSION_TIMEOUT_SECONDS_DEFAULT,
)

try:
    _cfg = ConfigManager(str(Path(__file__).parent.parent)).global_config
    MAX_BATCH_SIZE: int = _cfg.mcp_batch_size
    BATCH_TIMEOUT_SECONDS: int = _cfg.mcp_batch_timeout_seconds
    SESSION_TIMEOUT_SECONDS: int = _cfg.mcp_session_timeout_seconds
except FileNotFoundError:
    MAX_BATCH_SIZE = MCP_BATCH_SIZE_DEFAULT
    BATCH_TIMEOUT_SECONDS = MCP_BATCH_TIMEOUT_SECONDS_DEFAULT
    SESSION_TIMEOUT_SECONDS = MCP_SESSION_TIMEOUT_SECONDS_DEFAULT
