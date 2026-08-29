"""Driven adapter: fetch Organizer items from Burp's MCP server."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.types import TextContent

from domain.tools.burp.mcp_ports import OrganizerItem

logger = logging.getLogger(__name__)


class BurpMcpError(Exception):
    """Raised when the Burp MCP tool call fails."""


def _parse_items(text: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON objects from Burp MCP."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except json.JSONDecodeError:
        pass
    items: list[dict[str, Any]] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


class BurpMcpClient:
    """Connects to Burp's MCP server via SSE per call.

    Connect-per-poll rather than persistent connection so
    dropped connections resolve naturally on the next cycle.
    """

    def __init__(self, mcp_url: str) -> None:
        self._url = mcp_url

    def fetch_items(self) -> list[OrganizerItem]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[OrganizerItem]:
        async with sse_client(self._url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_organizer_items",
                    arguments={"offset": 0, "count": 1000},
                )

        if result.isError:
            raise BurpMcpError("get_organizer_items returned an error")

        text = ""
        for content in result.content:
            if isinstance(content, TextContent):
                text += content.text

        if not text:
            return []

        items_data: list[dict[str, Any]] = _parse_items(text)
        return [
            OrganizerItem(
                id=item["id"],
                status=item.get("status", ""),
                request=item.get("request", ""),
                response=item.get("response", ""),
                notes=item.get("notes", ""),
            )
            for item in items_data
        ]
