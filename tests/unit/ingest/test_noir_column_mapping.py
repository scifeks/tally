"""Tests for the Noir parser/handler post-Phase-9.

Phase 9 routes Noir output into ``url_findings`` via
``UrlInventoryIngestHandler``; ``NoirHandler.normalize`` is therefore a
no-op. The pieces that survive — vendor-path filtering inside
``parse_output``, and the ``_uri_only`` URL canonicalizer — still need
direct coverage.
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


class TestNoirHandlerNormalize:
    """Phase 9: ``normalize`` returns ``[]`` regardless of input."""

    def test_normalize_returns_empty_for_real_endpoint(self) -> None:
        handler = NoirHandler()
        assert handler.normalize(_make_result([_ENDPOINT]), profile="myrepo") == []

    def test_normalize_returns_empty_for_no_endpoints(self) -> None:
        handler = NoirHandler()
        assert handler.normalize(_make_result([]), profile="myrepo") == []


class TestVendorPathFilter:
    """Vendor/dependency paths are filtered inside ``parse_output``."""

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
        """Vendor paths are excluded in parse_output."""
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


class TestUriOnlyHelper:
    """``_uri_only()`` must strip host/scheme/port from any input."""

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
