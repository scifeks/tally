"""Tests for NoirHandler column mapping and URI-only enforcement.

Covers:
- All required columns are present in normalized rows
- url column contains only the URI path (no host/scheme/port)
- enriched is always False
- unmapped endpoint data lands in the row (goes to meta on upsert)
- domain and segment are correct
"""

from __future__ import annotations

from pathlib import Path

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.noir import (
    NoirHandler,
    _uri_only,
)
from infrastructure.tools.parsers.noir import (
    is_vendor_or_dependency_path as _is_vendor_or_dependency_path,
)
from infrastructure.tools.wrappers.local.noir import NoirLocalTool

_TIMESTAMP = "2026-04-03T00:00:00"


def _make_result(endpoints: list[dict]) -> ToolResult:
    return ToolResult(
        tool_name="noir",
        success=True,
        output="",
        parsed_data={
            "endpoints": endpoints,
            "summary": {"total_endpoints": len(endpoints), "total_paths": 1},
        },
        output_files={},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


_ENDPOINT = {
    "path": "/api/users/:id",
    "method": "get",
    "path_params": [{"name": "id", "type": "string"}],
    "query_params": [],
    "header_params": [],
    "cookie_params": [],
    "body_params": [],
}


class TestNoirColumnMapping:
    def _row(self) -> dict:
        handler = NoirHandler()
        rows = handler.normalize(_make_result([_ENDPOINT]), profile="myrepo")
        assert rows
        return rows[0]

    def test_tool_column(self) -> None:
        assert self._row()["tool"] == "noir"

    def test_finding_type_informational(self) -> None:
        assert self._row()["finding_type"] == '["informational"]'

    def test_severity_informational(self) -> None:
        assert self._row()["severity"] == "informational"

    def test_confidence_confirmed(self) -> None:
        assert self._row()["confidence"] == "confirmed"

    def test_url_is_uri_only(self) -> None:
        row = self._row()
        url = row["url"]
        assert url.startswith("/"), f"url must be a path, got: {url!r}"
        assert "://" not in url, f"url must not contain scheme, got: {url!r}"

    def test_method_uppercased(self) -> None:
        assert self._row()["method"] == "GET"

    def test_domain_is_code(self) -> None:
        assert self._row()["domain"] == "code"

    def test_segment_is_web(self) -> None:
        assert self._row()["segment"] == "web"

    def test_enriched_is_false(self) -> None:
        assert self._row()["enriched"] is False

    def test_description_present(self) -> None:
        row = self._row()
        assert "description" in row
        assert row["description"]

    def test_path_param_in_description(self) -> None:
        row = self._row()
        assert "id" in row["description"]

    def test_profile_present(self) -> None:
        row = self._row()
        assert row["profile"] == "myrepo"


class TestVendorPathFilter:
    """Vendor/dependency paths must not appear in normalized findings."""

    _VENDOR_PATHS = [
        "/vendor/lib/router.php",
        "/node_modules/react/index.js",
        "/venv/lib/python.py",
        "/.venv/bin/activate",
        "/site-packages/django/views.py",
        "/__pycache__/module.pyc",
        "/build/artifact.zip",
        "/dist/package.tar.gz",
        "/.git/config",
    ]
    _LEGIT_PATHS = [
        "/api/users",
        "/vendor-api/users",  # contains "vendor" but not as directory segment
        "/node/index.js",  # not /node_modules/
        "/builds",  # prefix match must not fire
    ]

    def test_vendor_detection(self) -> None:
        for path in self._VENDOR_PATHS:
            assert _is_vendor_or_dependency_path(path), (
                f"Should detect vendor: {path!r}"
            )

    def test_legit_not_detected(self) -> None:
        for path in self._LEGIT_PATHS:
            assert not _is_vendor_or_dependency_path(path), f"False positive: {path!r}"

    def test_vendor_paths_filtered_in_parse_output(self, tmp_path: Path) -> None:
        """Vendor paths are excluded in parse_output, before normalize sees them."""
        import json

        endpoints = [
            {"path": "/api/users", "method": "get", "parameters": []},
            {
                "path": "/vendor/sabberworm/php-css-parser/src/Renderable.php",
                "method": "post",
                "parameters": [],
            },
        ]
        oas3 = {
            "openapi": "3.0.0",
            "paths": {ep["path"]: {ep["method"]: {}} for ep in endpoints},
        }
        report = tmp_path / "report.json"
        report.write_text(json.dumps(oas3))

        tool = NoirLocalTool()
        tool._last_report_path = report
        parsed = tool.parse_output("", {})
        assert len(parsed["endpoints"]) == 1
        assert parsed["endpoints"][0]["path"] == "/api/users"

    def test_normalize_passes_through_all_received_endpoints(self) -> None:
        """normalize no longer filters — parse_output already cleaned the data."""
        endpoints = [
            {
                "path": "/api/users",
                "method": "GET",
                "path_params": [],
                "query_params": [],
                "header_params": [],
                "cookie_params": [],
                "body_params": [],
            },
            {
                "path": "/api/posts",
                "method": "POST",
                "path_params": [],
                "query_params": [],
                "header_params": [],
                "cookie_params": [],
                "body_params": [],
            },
        ]
        handler = NoirHandler()
        rows = handler.normalize(_make_result(endpoints), profile="test")
        assert len(rows) == 2


class TestUriOnlyHelper:
    """_uri_only() must strip host/scheme/port from any input."""

    def test_relative_path_unchanged(self) -> None:
        assert _uri_only("/api/users") == "/api/users"

    def test_full_url_stripped(self) -> None:
        assert _uri_only("http://localhost:9090/api/users") == "/api/users"

    def test_https_stripped(self) -> None:
        assert _uri_only("https://example.com/v1/items") == "/v1/items"

    def test_empty_string_unchanged(self) -> None:
        assert _uri_only("") == ""

    def test_query_string_preserved(self) -> None:
        result = _uri_only("http://host/search?q=foo")
        assert result == "/search?q=foo"

    def test_fragment_preserved(self) -> None:
        result = _uri_only("http://host/page#section")
        assert result == "/page#section"

    def test_path_param_preserved(self) -> None:
        result = _uri_only("http://host:8080/api/users/:id")
        assert result == "/api/users/:id"

    def test_url_in_normalize_is_uri_only(self) -> None:
        """Full-URL path field is sanitised to URI during normalize()."""
        endpoint_with_full_url = {
            "path": "http://localhost:9090/api/test",
            "method": "POST",
            "path_params": [],
            "query_params": [],
            "header_params": [],
            "cookie_params": [],
            "body_params": [],
        }
        handler = NoirHandler()
        rows = handler.normalize(_make_result([endpoint_with_full_url]), profile="t")
        assert rows[0]["url"] == "/api/test"
        assert "://" not in rows[0]["url"]
