from pathlib import Path

from core.config.manager import ConfigManager

try:
    _cfg = ConfigManager(str(Path(__file__).parent.parent)).global_config
    MAX_BATCH_SIZE: int = _cfg.mcp_batch_size
    BATCH_TIMEOUT_SECONDS: int = _cfg.mcp_batch_timeout_seconds
    SESSION_TIMEOUT_SECONDS: int = _cfg.mcp_session_timeout_seconds
except FileNotFoundError:
    MAX_BATCH_SIZE = 10
    BATCH_TIMEOUT_SECONDS = 30
    SESSION_TIMEOUT_SECONDS = 300
