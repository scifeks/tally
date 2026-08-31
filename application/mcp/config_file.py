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
) -> ShowConfigOutput:
    """Build the two setup options for Claude Code.

    Returns a JSON snippet for ~/.claude.json and a
    claude mcp add-json CLI command, both using
    ${TALLY_MCP_TOKEN} as the bearer token placeholder.
    """
    url = f"http://{host}:{port}/mcp"
    entry = {
        "type": "http",
        "url": url,
        "headers": {
            "Authorization": "Bearer ${TALLY_MCP_TOKEN}",
        },
    }
    snippet = json.dumps({"tally": entry}, indent=2)
    compact = json.dumps(entry, separators=(",", ":"))
    cli_cmd = f"claude mcp add-json tally '{compact}' --scope user"
    return ShowConfigOutput(
        json_snippet=snippet,
        cli_command=cli_cmd,
    )
