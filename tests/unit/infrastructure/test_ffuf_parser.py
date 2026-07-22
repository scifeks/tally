"""Unit tests for the ffuf JSON parser."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.parsers.ffuf import (
    parse_ffuf_json,
    parse_ffuf_json_string,
)

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "ingest" / "ffuf_output.json"
)


class TestParseFfufJsonString:
    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_ffuf_json_string("not json")
        assert "error" in result

    def test_empty_string_returns_empty_findings(self) -> None:
        result = parse_ffuf_json_string("")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_no_results_key_returns_empty_findings(self) -> None:
        result = parse_ffuf_json_string("{}")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_empty_results_returns_empty_findings(self) -> None:
        result = parse_ffuf_json_string('{"results": []}')
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_status_200_severity_informational(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 15,
                    "content-type": "text/html",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "admin"},
                }
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        finding = result["findings"][0]
        assert finding["severity"] == "informational"

    def test_status_403_severity_low(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/api",
                    "status": 403,
                    "length": 89,
                    "words": 10,
                    "lines": 1,
                    "content-type": "application/json",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "api"},
                }
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        finding = result["findings"][0]
        assert finding["severity"] == "low"

    def test_field_extraction_url_and_status(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 15,
                    "content-type": "text/html",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "admin"},
                }
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        finding = result["findings"][0]
        assert finding["url"] == "https://target.com/admin"
        assert finding["status"] == 200

    def test_field_extraction_content_type(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 15,
                    "content-type": "text/html",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "admin"},
                }
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        finding = result["findings"][0]
        assert finding["content_type"] == "text/html"

    def test_field_extraction_redirect_location(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/login",
                    "status": 302,
                    "length": 0,
                    "words": 0,
                    "lines": 0,
                    "content-type": "text/html; charset=UTF-8",
                    "redirectlocation": "https://target.com/auth",
                    "host": "target.com",
                    "input": {"FUZZ": "login"},
                }
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        finding = result["findings"][0]
        assert finding["redirect_location"] == "https://target.com/auth"

    def test_field_extraction_host(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 15,
                    "content-type": "text/html",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "admin"},
                }
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        finding = result["findings"][0]
        assert finding["host"] == "target.com"

    def test_multiple_results_counted(self) -> None:
        data = {
            "results": [
                {
                    "url": "https://target.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 15,
                    "content-type": "text/html",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "admin"},
                },
                {
                    "url": "https://target.com/api",
                    "status": 403,
                    "length": 89,
                    "words": 10,
                    "lines": 1,
                    "content-type": "application/json",
                    "redirectlocation": "",
                    "host": "target.com",
                    "input": {"FUZZ": "api"},
                },
            ]
        }
        result = parse_ffuf_json_string(json.dumps(data))
        assert result["summary"]["total_findings"] == 2


class TestParseFfufJson:
    def test_fixture_file_parses_correctly(self) -> None:
        result = parse_ffuf_json(FIXTURE)
        assert result["summary"]["total_findings"] == 3
        findings = result["findings"]
        assert len(findings) == 3
        assert findings[0]["url"] == "https://target.com/admin"
        assert findings[1]["url"] == "https://target.com/login"
        assert findings[2]["url"] == "https://target.com/api"

    def test_missing_file_returns_error(self) -> None:
        missing_path = Path("/nonexistent/path/ffuf.json")
        result = parse_ffuf_json(missing_path)
        assert "error" in result


class TestFfufHandler:
    def test_tool_name(self) -> None:
        from infrastructure.tools.parsers.ffuf import FfufHandler

        handler = FfufHandler()
        assert handler.tool_name == "ffuf"

    def test_domain_and_segment(self) -> None:
        from infrastructure.tools.parsers.ffuf import FfufHandler

        handler = FfufHandler()
        assert handler.domain == "web"
        assert handler.segment == "web"

    def test_render_includes_url_and_status(self) -> None:
        from infrastructure.tools.parsers.ffuf import FfufHandler

        handler = FfufHandler()
        finding = {
            "url": "https://target.com/admin",
            "status": 200,
            "severity": "informational",
        }
        rendered = handler.render(finding)
        assert "https://target.com/admin" in rendered
        assert "200" in rendered

    def test_fingerprint_key_is_stable(self) -> None:
        from infrastructure.tools.parsers.ffuf import FfufHandler

        handler = FfufHandler()
        finding = {
            "url": "https://target.com/admin",
            "status": 200,
        }
        key = handler.fingerprint_key(finding)
        key2 = handler.fingerprint_key(finding)
        assert key == key2

    def test_fingerprint_key_differs_by_url(self) -> None:
        from infrastructure.tools.parsers.ffuf import FfufHandler

        handler = FfufHandler()
        finding1 = {"url": "https://target.com/admin", "status": 200}
        finding2 = {"url": "https://target.com/api", "status": 200}
        key1 = handler.fingerprint_key(finding1)
        key2 = handler.fingerprint_key(finding2)
        assert key1 != key2

    def test_fingerprint_key_differs_by_status(self) -> None:
        from infrastructure.tools.parsers.ffuf import FfufHandler

        handler = FfufHandler()
        finding1 = {"url": "https://target.com/admin", "status": 200}
        finding2 = {"url": "https://target.com/admin", "status": 403}
        key1 = handler.fingerprint_key(finding1)
        key2 = handler.fingerprint_key(finding2)
        assert key1 != key2
