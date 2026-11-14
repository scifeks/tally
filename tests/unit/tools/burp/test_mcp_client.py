"""Unit tests for BurpMcpClient."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from mcp.types import TextContent  # noqa: E402

from domain.tools.burp.mcp_ports import OrganizerItem  # noqa: E402
from infrastructure.tools.burp.mcp_client import (  # noqa: E402
    BurpMcpClient,
    BurpMcpError,
)

_MODULE = "infrastructure.tools.burp.mcp_client"


def _make_text_result(data: list[dict]) -> MagicMock:
    """Build a mock CallToolResult with JSON text content."""
    content_item = TextContent(type="text", text=json.dumps(data))
    result = MagicMock()
    result.content = [content_item]
    result.is_error = False
    return result


@pytest.fixture()
def mock_mcp_session() -> Iterator[AsyncMock]:
    """Patch sse_client and ClientSession, yield the mock session."""
    session = AsyncMock()
    sse_ctx = AsyncMock()
    sse_ctx.__aenter__.return_value = (
        MagicMock(),
        MagicMock(),
    )
    cls_ctx = AsyncMock()
    cls_ctx.__aenter__.return_value = session

    with (
        patch(f"{_MODULE}.sse_client", return_value=sse_ctx),
        patch(
            f"{_MODULE}.ClientSession",
            return_value=cls_ctx,
        ),
    ):
        yield session


_SAMPLE_ITEMS = [
    {
        "id": 1,
        "status": "New",
        "request": "GET /login HTTP/1.1\r\nHost: target.app",
        "response": "HTTP/1.1 200 OK\r\n\r\n<html>",
        "notes": "found reflected XSS in search param",
    },
    {
        "id": 5,
        "status": "New",
        "request": "POST /api/users HTTP/1.1",
        "response": "<no response>",
        "notes": "",
    },
]


class TestBurpMcpClientFetchItems:
    def test_parses_valid_response(self, mock_mcp_session: AsyncMock) -> None:
        mock_mcp_session.call_tool.return_value = _make_text_result(_SAMPLE_ITEMS)
        client = BurpMcpClient("http://localhost:9876/sse")
        items = client.fetch_items()

        assert len(items) == 2
        assert items[0] == OrganizerItem(
            id=1,
            status="New",
            request="GET /login HTTP/1.1\r\nHost: target.app",
            response="HTTP/1.1 200 OK\r\n\r\n<html>",
            notes="found reflected XSS in search param",
        )
        assert items[1].id == 5
        assert items[1].response == "<no response>"
        assert items[1].notes == ""

    def test_empty_response_returns_empty_list(
        self, mock_mcp_session: AsyncMock
    ) -> None:
        mock_mcp_session.call_tool.return_value = _make_text_result([])
        client = BurpMcpClient("http://localhost:9876/sse")
        assert client.fetch_items() == []

    def test_error_result_raises(self, mock_mcp_session: AsyncMock) -> None:
        result = MagicMock()
        result.is_error = True
        result.content = []
        mock_mcp_session.call_tool.return_value = result

        client = BurpMcpClient("http://localhost:9876/sse")
        with pytest.raises(BurpMcpError):
            client.fetch_items()

    def test_connection_error_propagates(self) -> None:
        sse_ctx = AsyncMock()
        sse_ctx.__aenter__.side_effect = ConnectionError("refused")
        with patch(f"{_MODULE}.sse_client", return_value=sse_ctx):
            client = BurpMcpClient("http://localhost:9876/sse")
            with pytest.raises(ConnectionError):
                client.fetch_items()

    def test_calls_correct_tool_name(self, mock_mcp_session: AsyncMock) -> None:
        mock_mcp_session.call_tool.return_value = _make_text_result([])
        client = BurpMcpClient("http://localhost:9876/sse")
        client.fetch_items()

        mock_mcp_session.call_tool.assert_called_once_with(
            "get_organizer_items",
            arguments={"offset": 0, "count": 1000},
        )
