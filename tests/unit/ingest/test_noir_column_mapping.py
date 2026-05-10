"""Tests for Noir parser/handler.

NoirHandler.normalize returns empty because URL routing is handled via
UrlInventoryIngestHandler. Vendor-path filtering moved to application
core; the parser re-exports the filter under a legacy alias for
backward compatibility. The _uri_only URL canonicalizer requires
direct test coverage.
"""

from __future__ import annotations

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.noir import (
    NoirHandler,
    _uri_only,
)
from infrastructure.tools.parsers.noir import (
    is_vendor_or_dependency_path as _is_vendor_or_dependency_path,
)

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
    """normalize returns [] regardless of input."""

    def test_normalize_returns_empty_for_real_endpoint(self) -> None:
        handler = NoirHandler()
        assert handler.normalize(_make_result([_ENDPOINT]), profile="myrepo") == []

    def test_normalize_returns_empty_for_no_endpoints(self) -> None:
        handler = NoirHandler()
        assert handler.normalize(_make_result([]), profile="myrepo") == []


class TestVendorPathFilterAlias:
    """Vendor-path filtering re-exported under legacy alias."""

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
