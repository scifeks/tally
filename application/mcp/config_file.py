"""Build and write .mcp.json for Claude Code integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_mcp_json(host: str, port: int) -> dict[str, Any]:
    """Return the .mcp.json content dict.

    ``host`` includes the protocol (e.g. ``http://127.0.0.1``).
    """
    url = f"{host.rstrip('/')}:{port}/sse"
    return {
        "mcpServers": {
            "tally": {
                "type": "sse",
                "url": url,
            }
        }
    }


def write_mcp_json(directory: Path, host: str, port: int) -> Path:
    """Write .mcp.json to ``directory`` if it does not exist.

    Returns the file path. Existing files are left untouched.
    """
    target = directory / ".mcp.json"
    if target.exists():
        return target
    content = build_mcp_json(host, port)
    target.write_text(json.dumps(content, indent=2) + "\n")
    return target
