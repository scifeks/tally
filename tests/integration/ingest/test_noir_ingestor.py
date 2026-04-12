"""Integration tests for NoirHandler.normalize() and render().

Follows the same pattern as tests/integration/ingest/test_zap.py.
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

    def test_normalize_returns_one_row_per_endpoint(
        self, fixture_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        expected = fixture_parsed_data["summary"]["total_endpoints"]
        assert len(rows) == expected

    def test_rows_have_correct_tool_and_profile(
        self, fixture_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        for row in rows:
            assert row["tool"] == "noir"
            assert row["profile"] == "dvna"

    def test_rows_have_informational_finding_type(
        self, fixture_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        for row in rows:
            assert row["finding_type"] == '["informational"]'
            assert row["severity"] == "informational"

    def test_rows_have_url_and_method(self, fixture_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        for row in rows:
            assert row["url"], f"url must not be empty: {row}"
            assert row["method"], f"method must not be empty: {row}"

    def test_login_post_row_includes_param_names(
        self, fixture_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        login_posts = [
            r for r in rows if r["url"] == "/login" and r["method"] == "POST"
        ]
        assert len(login_posts) == 1
        desc = login_posts[0]["description"]
        assert "username" in desc or "password" in desc

    def test_normalize_is_idempotent(self, fixture_parsed_data: dict) -> None:
        """Calling normalize twice on the same result produces identical rows."""
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows1 = handler.normalize(result, profile="dvna")
        rows2 = handler.normalize(result, profile="dvna")
        assert rows1 == rows2

    def test_empty_parsed_data_returns_empty_list(self) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result({"endpoints": [], "summary": {"total_endpoints": 0}})
        rows = handler.normalize(result, profile="dvna")
        assert rows == []

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
        rows = handler.normalize(result, profile="dvna")
        assert rows == []

    def test_source_file_preserved_from_output_files(
        self, fixture_parsed_data: dict, tmp_path: Path
    ) -> None:
        oas3_path = tmp_path / "dvna_oas3.json"
        oas3_path.write_text("{}", encoding="utf-8")
        result = _make_noir_result(
            fixture_parsed_data, output_files={"stdout": oas3_path}
        )
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        rows = handler.normalize(result, profile="dvna")
        for row in rows:
            assert row["source_file"] == str(oas3_path)

    def test_render_returns_string_for_every_row(
        self, fixture_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        for row in rows:
            text = handler.render(row)
            assert isinstance(text, str)
            assert "[noir]" in text

    def test_render_includes_method_and_path(self, fixture_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("noir")
        assert handler is not None
        result = _make_noir_result(fixture_parsed_data)
        rows = handler.normalize(result, profile="dvna")
        for row in rows:
            text = handler.render(row)
            assert row["method"] in text
            assert row["url"] in text
