"""Unit tests for the Katana parser and KatanaHandler."""

from __future__ import annotations

import json
from pathlib import Path

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.katana import (
    KatanaHandler,
    parse_katana_jsonl,
    parse_katana_jsonl_string,
)

_TIMESTAMP = "2026-04-13T00:00:00"


# Helpers


def _katana_line(
    endpoint: str = "http://localhost:8080/api/users",
    method: str = "GET",
    status_code: int = 200,
    content_type: str | None = "application/json",
) -> str:
    record: dict = {
        "timestamp": "2026-04-13T00:00:00.000Z",
        "request": {
            "method": method,
            "endpoint": endpoint,
            "raw": f"{method} /api/users HTTP/1.1\r\n",
        },
        "response": {
            "status_code": status_code,
            "headers": ({"content-type": content_type} if content_type else {}),
            "body": "",
            "content_length": 0,
        },
    }
    return json.dumps(record)


def _make_result(endpoints: list[dict]) -> ToolResult:
    return ToolResult(
        tool_name="katana",
        success=True,
        output="",
        parsed_data={
            "endpoints": endpoints,
            "summary": {"total_endpoints": len(endpoints)},
        },
        output_files={},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


# parse_katana_jsonl_string


class TestParseKatanaJsonlString:
    def test_empty_string_returns_empty_endpoints(self) -> None:
        result = parse_katana_jsonl_string("")
        assert result["endpoints"] == []
        assert result["summary"]["total_endpoints"] == 0

    def test_whitespace_only_returns_empty(self) -> None:
        result = parse_katana_jsonl_string("   \n   \n")
        assert result["endpoints"] == []

    def test_single_get_endpoint_parsed(self) -> None:
        line = _katana_line("http://localhost:8080/api/users", "GET", 200)
        result = parse_katana_jsonl_string(line)
        assert len(result["endpoints"]) == 1
        ep = result["endpoints"][0]
        assert ep["url"] == "http://localhost:8080/api/users"
        assert ep["path"] == "/api/users"
        assert ep["method"] == "GET"
        assert ep["status_code"] == 200

    def test_post_endpoint_parsed(self) -> None:
        line = _katana_line("http://localhost:8080/api/items", "POST", 201)
        result = parse_katana_jsonl_string(line)
        ep = result["endpoints"][0]
        assert ep["method"] == "POST"
        assert ep["status_code"] == 201

    def test_content_type_extracted(self) -> None:
        line = _katana_line(content_type="text/html")
        result = parse_katana_jsonl_string(line)
        assert result["endpoints"][0]["content_type"] == "text/html"

    def test_missing_content_type_is_none(self) -> None:
        line = _katana_line(content_type=None)
        result = parse_katana_jsonl_string(line)
        assert result["endpoints"][0]["content_type"] is None

    def test_multiple_lines_all_parsed(self) -> None:
        lines = "\n".join(
            [
                _katana_line("http://localhost:8080/a", "GET"),
                _katana_line("http://localhost:8080/b", "POST"),
                _katana_line("http://localhost:8080/c", "PUT"),
            ]
        )
        result = parse_katana_jsonl_string(lines)
        assert len(result["endpoints"]) == 3
        assert result["summary"]["total_endpoints"] == 3

    def test_malformed_json_line_skipped(self) -> None:
        valid = _katana_line("http://localhost:8080/api/ok", "GET")
        jsonl = "not-json\n" + valid
        result = parse_katana_jsonl_string(jsonl)
        assert len(result["endpoints"]) == 1

    def test_line_missing_request_field_skipped(self) -> None:
        bad = json.dumps({"timestamp": "...", "response": {}})
        valid = _katana_line()
        result = parse_katana_jsonl_string(bad + "\n" + valid)
        assert len(result["endpoints"]) == 1

    def test_line_missing_endpoint_field_skipped(self) -> None:
        bad = json.dumps({"request": {"method": "GET", "raw": ""}, "response": {}})
        valid = _katana_line()
        result = parse_katana_jsonl_string(bad + "\n" + valid)
        assert len(result["endpoints"]) == 1

    def test_method_uppercased(self) -> None:
        line = _katana_line(method="get")
        result = parse_katana_jsonl_string(line)
        assert result["endpoints"][0]["method"] == "GET"

    def test_path_extracted_from_url(self) -> None:
        line = _katana_line("http://localhost:8080/api/v1/users?page=1")
        result = parse_katana_jsonl_string(line)
        assert result["endpoints"][0]["path"] == "/api/v1/users"


# parse_katana_jsonl (file-based)


class TestParseKatanaJsonl:
    def test_reads_file_and_returns_endpoints(self, tmp_path: Path) -> None:
        f = tmp_path / "out.jsonl"
        f.write_text(_katana_line(), encoding="utf-8")
        result = parse_katana_jsonl(f)
        assert len(result["endpoints"]) == 1

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        result = parse_katana_jsonl(tmp_path / "nonexistent.jsonl")
        assert "error" in result
        assert result["endpoints"] == []

    def test_empty_file_returns_empty_endpoints(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        result = parse_katana_jsonl(f)
        assert result["endpoints"] == []


# KatanaHandler: meta


class TestKatanaHandlerMeta:
    def test_tool_name(self) -> None:
        assert KatanaHandler.tool_name == "katana"

    def test_domain_is_web(self) -> None:
        assert KatanaHandler.domain == "web"

    def test_segment_is_web(self) -> None:
        assert KatanaHandler.segment == "web"

    def test_should_enrich_false(self) -> None:
        assert KatanaHandler.should_enrich is False

    def test_should_visualize_false(self) -> None:
        assert KatanaHandler.should_visualize is False

    def test_type_informational_true(self) -> None:
        from infrastructure.tools.parsers._shared import _shared_meta

        handler = KatanaHandler()
        meta = _shared_meta(handler, "informational")
        assert meta["type_informational"] is False  # empty set in type_flags

    def test_shared_meta_enriched_false(self) -> None:
        from infrastructure.tools.parsers._shared import _shared_meta

        handler = KatanaHandler()
        meta = _shared_meta(handler, "informational")
        assert meta["enriched"] is False

    def test_shared_meta_domain_web(self) -> None:
        from infrastructure.tools.parsers._shared import _shared_meta

        handler = KatanaHandler()
        meta = _shared_meta(handler, "informational")
        assert meta["domain"] == "web"

    def test_shared_meta_segment_web(self) -> None:
        from infrastructure.tools.parsers._shared import _shared_meta

        handler = KatanaHandler()
        meta = _shared_meta(handler, "informational")
        assert meta["segment"] == "web"


# KatanaHandler: normalize


class TestKatanaHandlerNormalize:
    """Phase 9: ``KatanaHandler.normalize`` is a no-op.

    Katana output is routed into ``url_findings`` via
    ``UrlInventoryIngestHandler``; it no longer emits ``findings`` rows.
    """

    def _endpoint(self) -> dict:
        return {
            "url": "http://localhost:8080/api/users",
            "path": "/api/users",
            "method": "GET",
            "status_code": 200,
            "content_type": "application/json",
        }

    def test_normalize_returns_empty(self) -> None:
        handler = KatanaHandler()
        result = _make_result([self._endpoint()])
        assert handler.normalize(result, profile="p") == []

    def test_empty_endpoints_returns_empty_rows(self) -> None:
        handler = KatanaHandler()
        result = _make_result([])
        assert handler.normalize(result, profile="p") == []


# KatanaHandler: fingerprint_key


class TestKatanaHandlerFingerprint:
    def test_key_format(self) -> None:
        handler = KatanaHandler()
        finding = {"method": "GET", "url": "http://localhost/api/users"}
        key = handler.fingerprint_key(finding)
        assert key == "katana|GET|http://localhost/api/users"

    def test_different_methods_different_keys(self) -> None:
        handler = KatanaHandler()
        key1 = handler.fingerprint_key({"method": "GET", "url": "http://h/a"})
        key2 = handler.fingerprint_key({"method": "POST", "url": "http://h/a"})
        assert key1 != key2

    def test_different_urls_different_keys(self) -> None:
        handler = KatanaHandler()
        key1 = handler.fingerprint_key({"method": "GET", "url": "http://h/a"})
        key2 = handler.fingerprint_key({"method": "GET", "url": "http://h/b"})
        assert key1 != key2


# KatanaHandler: render


class TestKatanaHandlerRender:
    def test_render_with_status_code(self) -> None:
        handler = KatanaHandler()
        row = {
            "method": "GET",
            "url": "http://localhost:8080/api/users",
            "status_code": 200,
        }
        rendered = handler.render(row)
        assert rendered == "[katana] GET http://localhost:8080/api/users (200)"

    def test_render_without_status_code(self) -> None:
        handler = KatanaHandler()
        row = {"method": "POST", "url": "http://localhost:8080/api/items"}
        rendered = handler.render(row)
        assert rendered == "[katana] POST http://localhost:8080/api/items"

    def test_render_zero_status_code_omitted(self) -> None:
        handler = KatanaHandler()
        row = {
            "method": "GET",
            "url": "http://localhost:8080/api",
            "status_code": 0,
        }
        rendered = handler.render(row)
        # status_code 0 is falsy → no parenthetical
        assert "(" not in rendered
