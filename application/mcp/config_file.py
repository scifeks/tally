"""Format Claude Code configuration snippets for MCP setup."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ShowConfigOutput:
    json_snippet: str
    cli_command: str


def format_show_config(
    host: str,
    port: int,
    token: str,
) -> ShowConfigOutput:
    """Build the ready-to-run setup command for Claude Code.

    The token is embedded in the output so the user can
    copy-paste a single command. The output is ephemeral
    terminal text, same security model as token creation.
    """
    url = f"http://{host}:{port}/mcp"
    entry = {
        "type": "http",
        "url": url,
        "headers": {
            "Authorization": f"Bearer {token}",
        },
    }
    snippet = json.dumps({"tally": entry}, indent=2)
    compact = json.dumps(entry, separators=(",", ":"))
    cli_cmd = f"claude mcp add-json tally '{compact}' --scope user"
    return ShowConfigOutput(
        json_snippet=snippet,
        cli_command=cli_cmd,
    )
