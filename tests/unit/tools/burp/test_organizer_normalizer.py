"""Unit tests for the Organizer HTTP normalizer."""

from __future__ import annotations

import pytest

from application.tools.burp.organizer_normalizer import normalize_http

_STANDARD_REQUEST = (
    "POST /WebGoat/login HTTP/1.1\r\n"
    "Host: goat.justinc.app\r\n"
    "Content-Type: application/x-www-form-urlencoded\r\n"
    "\r\n"
    "username=admin&password=admin"
)
_STANDARD_RESPONSE = "HTTP/1.1 302 Found\r\nLocation: /WebGoat/welcome\r\n"


class TestNormalizeHttp:
    def test_extracts_method_url_host_status(self) -> None:
        result = normalize_http(_STANDARD_REQUEST, _STANDARD_RESPONSE)
        assert result.method == "POST"
        assert result.url == "/WebGoat/login"
        assert result.host == "goat.justinc.app"
        assert result.status_code == 302

    def test_no_response_yields_none_status(self) -> None:
        result = normalize_http(_STANDARD_REQUEST, "<no response>")
        assert result.status_code is None
        assert result.method == "POST"

    @pytest.mark.parametrize(
        ("request_str", "expected_method", "expected_url"),
        [
            ("", "", ""),
            ("GARBAGE", "", ""),
            ("GET", "", ""),
            ("GET /path HTTP/1.1", "GET", "/path"),
        ],
        ids=["empty", "single-token", "method-only", "well-formed"],
    )
    def test_malformed_request_line(
        self,
        request_str: str,
        expected_method: str,
        expected_url: str,
    ) -> None:
        result = normalize_http(request_str, "<no response>")
        assert result.method == expected_method
        assert result.url == expected_url
        assert result.host is None

    @pytest.mark.parametrize(
        ("response_str", "expected"),
        [
            ("HTTP/1.1 200 OK", 200),
            ("HTTP/2 404 Not Found", 404),
            ("", None),
            ("<no response>", None),
            ("garbage response", None),
            ("HTTP/1.1 notanint OK", None),
        ],
        ids=["ok", "http2", "empty", "no-response", "garbage", "bad-status"],
    )
    def test_response_status_parsing(
        self,
        response_str: str,
        expected: int | None,
    ) -> None:
        result = normalize_http("GET / HTTP/1.1", response_str)
        assert result.status_code == expected
