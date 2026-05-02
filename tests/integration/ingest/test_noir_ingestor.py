"""Integration tests for ``NoirHandler``.

Noir routes output into ``url_findings`` via ``UrlInventoryIngestHandler``
instead of emitting rows into ``findings``. The handler's ``normalize`` is
therefore a no-op, and ``render`` continues to render arbitrary URL
metadata for any caller that pre-builds rows itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.noir import parse_noir_json  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
_TIMESTAMP = "2026-04-03T00:00:00"


def _make_noir_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="noir",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.5,
    )


@pytest.fixture()
def fixture_parsed_data() -> dict:
    return parse_noir_json(_FIXTURES / "noir_oas3.json")


class TestNoirIngestor:
    def test_handler_loads_via_factory(self) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        assert handler.tool_name == "noir"

    def test_normalize_returns_empty_post_phase_9(
        self, fixture_parsed_data: dict
    ) -> None:
        """Noir is URL-discovery only; ``normalize`` emits no findings."""
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        assert handler.normalize(result, profile="dvna") == []

    def test_empty_parsed_data_returns_empty_list(self) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result({"endpoints": [], "summary": {"total_endpoints": 0}})
        assert handler.normalize(result, profile="dvna") == []

    def test_none_parsed_data_returns_empty_list(self) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = ToolResult(
            tool_name="noir",
            success=True,
            output="",
            parsed_data=None,
            output_files={},
            timestamp=_TIMESTAMP,
            duration_seconds=0.0,
        )
        assert handler.normalize(result, profile="dvna") == []

    def test_render_includes_method_and_url(self) -> None:
        """``render`` works on hand-built rows for any caller."""
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        text = handler.render(
            {"method": "POST", "url": "/login", "description": "auth"}
        )
        assert "[noir]" in text
        assert "POST" in text
        assert "/login" in text
