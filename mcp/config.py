from pathlib import Path

from core.config.manager import ConfigManager

_cfg = ConfigManager(str(Path(__file__).parent.parent)).global_config
MAX_BATCH_SIZE: int = _cfg.mcp_batch_size
BATCH_TIMEOUT_SECONDS: int = _cfg.mcp_batch_timeout_seconds
