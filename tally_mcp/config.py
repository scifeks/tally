from pathlib import Path

from application.config.mcp_defaults import load_mcp_defaults

MAX_BATCH_SIZE, BATCH_TIMEOUT_SECONDS, SESSION_TIMEOUT_SECONDS = load_mcp_defaults(
    str(Path(__file__).parent.parent)
)
