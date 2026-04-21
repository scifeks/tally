"""Unit tests for the XSStrike log parser (infrastructure.tools.parsers.xsstrike)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.xsstrike import (
    XSSTrikeHandler,
    _parse_xsstrike_lines,
    _strip_ansi,
    parse_xsstrike_log,
    parse_xsstrike_log_string,
)

# ---------------------------------------------------------------------------
# _strip_ansi
# ---------------------------------------------------------------------------


class TestStripAnsi:
    def test_removes_color_codes(self) -> None:
        line = "\x1b[32mVulnerable webpage: http://x.com\x1b[0m"
        assert _strip_ansi(line) == "Vulnerable webpage: http://x.com"

    def test_plain_line_unchanged(self) -> None:
        line = "2024-01-01 12:00:00 xsstrike - INFO - started"
        assert _strip_ansi(line) == line

    def test_empty_string_returns_empty(self) -> None:
        assert _strip_ansi("") == ""

    def test_only_ansi_codes_returns_empty(self) -> None:
        assert _strip_ansi("\x1b[32m\x1b[0m") == ""


# ---------------------------------------------------------------------------
# parse_xsstrike_log_string — empty / malformed inputs
# ---------------------------------------------------------------------------


class TestParseXSSTrikeLogStringEdgeCases:
    def test_empty_string_returns_empty_findings(self) -> None:
        result = parse_xsstrike_log_string("")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_whitespace_only_returns_empty_findings(self) -> None:
        result = parse_xsstrike_log_string("   \n\n\t  ")
        assert result["findings"] == []

    def test_no_vuln_lines_returns_empty_findings(self) -> None:
        log = (
            "2024-01-01 12:00:00 xsstrike - INFO - Starting\n"
            "2024-01-01 12:00:01 xsstrike - DEBUG - Crawling\n"
        )
        result = parse_xsstrike_log_string(log)
        assert result["findings"] == []

    def test_non_vuln_lines_between_pairs_are_ignored(self) -> None:
        log = (
            "2024-01-01 12:00:01 xsstrike - INFO - some info\n"
            "2024-01-01 12:00:02 xsstrike - VULN - Vulnerable webpage: http://x.com/s\n"
            "2024-01-01 12:00:02 xsstrike - DEBUG - doing stuff\n"
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vector for q: <script>alert(1)</script>\n"
        )
        # DEBUG line between URL and vector — the pair is NOT consecutive;
        # the URL becomes pending and is replaced.  Vector then has no URL → skipped.
        result = parse_xsstrike_log_string(log)
        # The pending_url is set to the VULN URL line.
        # The DEBUG line is neither URL nor vector — pending_url stays.
        # The vector line matches and closes the pair.
        assert len(result["findings"]) == 1
        assert result["findings"][0]["url"] == "http://x.com/s"


# ---------------------------------------------------------------------------
# parse_xsstrike_log_string — valid VULN pairs
# ---------------------------------------------------------------------------


class TestParseXSSTrikeLogStringValidPairs:
    def test_single_vuln_pair_produces_one_finding(self) -> None:
        log = (
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/search\n"
            "2024-01-01 12:00:02 xsstrike - VULN - Vector for q: "
            "<img src=x onerror=alert(1)>\n"
        )
        result = parse_xsstrike_log_string(log)
        assert len(result["findings"]) == 1
        finding = result["findings"][0]
        assert finding["url"] == "https://app.example.com/search"
        assert finding["param"] == "q"
        assert finding["payload"] == "<img src=x onerror=alert(1)>"

    def test_two_vuln_pairs_produce_two_findings(self) -> None:
        log = (
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/search\n"
            "2024-01-01 12:00:02 xsstrike - VULN - Vector for q: "
            "<img src=x onerror=alert(1)>\n"
            "2024-01-01 12:00:04 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/profile\n"
            "2024-01-01 12:00:04 xsstrike - VULN - Vector for name: "
            '"><svg onload=alert(document.domain)>\n'
        )
        result = parse_xsstrike_log_string(log)
        assert len(result["findings"]) == 2

    def test_summary_total_matches_finding_count(self) -> None:
        log = (
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/search\n"
            "2024-01-01 12:00:02 xsstrike - VULN - Vector for q: payload\n"
        )
        result = parse_xsstrike_log_string(log)
        assert result["summary"]["total_findings"] == len(result["findings"])

    def test_ansi_codes_stripped_before_matching(self) -> None:
        log = (
            "\x1b[32m2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/s\x1b[0m\n"
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vector for \x1b[32mp\x1b[0m: <script>x</script>\n"
        )
        result = parse_xsstrike_log_string(log)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["url"] == "https://app.example.com/s"
        assert result["findings"][0]["param"] == "p"

    def test_console_format_vuln_pair_parsed(self) -> None:
        """Console (Docker) log format: [++] prefix instead of timestamp."""
        log = (
            "[++] Vulnerable webpage: https://app.example.com/login\n"
            "[++] Vector for user: <img src=x onerror=alert(1)>\n"
        )
        result = parse_xsstrike_log_string(log)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["url"] == "https://app.example.com/login"
        assert result["findings"][0]["param"] == "user"

    def test_field_keys_present_on_each_finding(self) -> None:
        log = (
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/s\n"
            "2024-01-01 12:00:02 xsstrike - VULN - Vector for q: payload\n"
        )
        result = parse_xsstrike_log_string(log)
        finding = result["findings"][0]
        assert "url" in finding
        assert "param" in finding
        assert "payload" in finding


# ---------------------------------------------------------------------------
# Unpaired lines
# ---------------------------------------------------------------------------


class TestUnpairedLines:
    def test_unpaired_url_line_is_skipped(self) -> None:
        log = (
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/s\n"
            "2024-01-01 12:00:03 xsstrike - INFO - something else\n"
        )
        result = parse_xsstrike_log_string(log)
        assert result["findings"] == []

    def test_unpaired_vector_line_is_skipped(self) -> None:
        log = "2024-01-01 12:00:02 xsstrike - VULN - Vector for q: payload\n"
        result = parse_xsstrike_log_string(log)
        assert result["findings"] == []

    def test_two_consecutive_url_lines_second_replaces_first(self) -> None:
        log = (
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/a\n"
            "2024-01-01 12:00:02 xsstrike - VULN - "
            "Vulnerable webpage: https://app.example.com/b\n"
            "2024-01-01 12:00:02 xsstrike - VULN - Vector for q: payload\n"
        )
        result = parse_xsstrike_log_string(log)
        # Only one finding — the second URL pairs with the vector.
        assert len(result["findings"]) == 1
        assert result["findings"][0]["url"] == "https://app.example.com/b"


# ---------------------------------------------------------------------------
# _parse_xsstrike_lines (internal)
# ---------------------------------------------------------------------------


class TestParseXSSTrikeLines:
    def test_empty_list_returns_empty_findings(self) -> None:
        result = _parse_xsstrike_lines([])
        assert result["findings"] == []

    def test_blank_lines_ignored(self) -> None:
        lines = ["", "   ", "\t"]
        result = _parse_xsstrike_lines(lines)
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# parse_xsstrike_log (file path)
# ---------------------------------------------------------------------------


class TestParseXSSTrikeLog:
    def test_reads_fixture_log(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "ingest"
            / "xsstrike_crawl.log"
        )
        result = parse_xsstrike_log(fixture)
        assert len(result["findings"]) == 2

    def test_fixture_finding_fields(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "ingest"
            / "xsstrike_crawl.log"
        )
        result = parse_xsstrike_log(fixture)
        urls = {f["url"] for f in result["findings"]}
        assert "https://app.example.com/search" in urls
        assert "https://app.example.com/profile" in urls

    def test_missing_file_returns_error_key(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such_file.log"
        result = parse_xsstrike_log(missing)
        assert "error" in result

    def test_empty_log_file_returns_empty_findings(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.log"
        empty.write_text("", encoding="utf-8")
        result = parse_xsstrike_log(empty)
        assert result["findings"] == []

    def test_log_file_with_no_findings_returns_empty(self, tmp_path: Path) -> None:
        log = tmp_path / "info_only.log"
        log.write_text(
            "2024-01-01 12:00:00 xsstrike - INFO - starting\n"
            "2024-01-01 12:00:01 xsstrike - DEBUG - crawling\n",
            encoding="utf-8",
        )
        result = parse_xsstrike_log(log)
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# parse_xsstrike_log_string — return structure
# ---------------------------------------------------------------------------


class TestReturnStructure:
    def test_always_has_findings_key(self) -> None:
        result = parse_xsstrike_log_string("random content")
        assert "findings" in result

    def test_always_has_component_findings_key(self) -> None:
        result = parse_xsstrike_log_string("random content")
        assert "component_findings" in result

    def test_always_has_summary_key(self) -> None:
        result = parse_xsstrike_log_string("random content")
        assert "summary" in result
        assert "total_findings" in result["summary"]

    @pytest.mark.parametrize("text", ["", "   ", "\n\n"])
    def test_empty_variants_return_zero_total(self, text: str) -> None:
        result = parse_xsstrike_log_string(text)
        assert result["summary"]["total_findings"] == 0


# ---------------------------------------------------------------------------
# RetireJs component findings
# ---------------------------------------------------------------------------

_RETIREJS_BLOCK = (
    "2026-04-12 19:30:11,523 plugins.retireJs - GOOD - "
    "Vulnerable component: jquery v3.2.1\n"
    "2026-04-12 19:30:11,523 plugins.retireJs - INFO - "
    "Component location: http://localhost:8080/static/js/jquery-3.2.1.min.js\n"
    "2026-04-12 19:30:11,523 plugins.retireJs - INFO - "
    "Total vulnerabilities: 1\n"
    "2026-04-12 19:30:11,523 plugins.retireJs - INFO - "
    "Summary: jQuery before 3.4.0, mishandles Object.prototype pollution\n"
    "2026-04-12 19:30:11,523 plugins.retireJs - INFO - Severity: low\n"
    "2026-04-12 19:30:11,523 plugins.retireJs - INFO - CVE: CVE-2019-11358\n"
)


class TestParseRetireJsFindings:
    def test_retirejs_block_produces_one_component_finding(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert len(result["component_findings"]) == 1

    def test_retirejs_extracts_component_name(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["component_findings"][0]["component_name"] == "jquery"

    def test_retirejs_extracts_component_version(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["component_findings"][0]["component_version"] == "3.2.1"

    def test_retirejs_extracts_cve(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["component_findings"][0]["cve"] == "CVE-2019-11358"

    def test_retirejs_extracts_severity(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["component_findings"][0]["severity"] == "low"

    def test_retirejs_extracts_component_location(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["component_findings"][0]["component_location"] == (
            "http://localhost:8080/static/js/jquery-3.2.1.min.js"
        )

    def test_retirejs_extracts_summary(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert "Object.prototype pollution" in (
            result["component_findings"][0].get("summary", "")
        )

    def test_retirejs_xss_findings_still_empty(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["findings"] == []

    def test_multiple_retirejs_blocks_produce_multiple_findings(self) -> None:
        second_block = (
            "2026-04-12 19:30:12,000 plugins.retireJs - GOOD - "
            "Vulnerable component: lodash v4.17.15\n"
            "2026-04-12 19:30:12,001 plugins.retireJs - INFO - "
            "Component location: http://localhost:8080/static/js/lodash.js\n"
            "2026-04-12 19:30:12,002 plugins.retireJs - INFO - Severity: high\n"
            "2026-04-12 19:30:12,003 plugins.retireJs - INFO - "
            "CVE: CVE-2021-23337\n"
        )
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK + second_block)
        assert len(result["component_findings"]) == 2

    def test_retirejs_mixed_with_vuln_pairs(self) -> None:
        vuln_pair = (
            "2026-04-12 19:30:15,000 xsstrike - VULN - "
            "Vulnerable webpage: http://localhost:8080/search\n"
            "2026-04-12 19:30:15,001 xsstrike - VULN - "
            "Vector for q: <script>alert(1)</script>\n"
        )
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK + vuln_pair)
        assert len(result["findings"]) == 1
        assert len(result["component_findings"]) == 1

    def test_total_findings_includes_component_findings(self) -> None:
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK)
        assert result["summary"]["total_findings"] == 1

    def test_total_findings_sums_both_types(self) -> None:
        vuln_pair = (
            "2026-04-12 19:30:15,000 xsstrike - VULN - "
            "Vulnerable webpage: http://localhost:8080/search\n"
            "2026-04-12 19:30:15,001 xsstrike - VULN - "
            "Vector for q: <script>alert(1)</script>\n"
        )
        result = parse_xsstrike_log_string(_RETIREJS_BLOCK + vuln_pair)
        assert result["summary"]["total_findings"] == 2

    def test_fixture_log_produces_component_finding(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "ingest"
            / "xsstrike_retirejs.log"
        )
        result = parse_xsstrike_log(fixture)
        assert len(result["component_findings"]) == 1
        assert result["component_findings"][0]["cve"] == "CVE-2019-11358"


# ---------------------------------------------------------------------------
# XSSTrikeHandler.normalize — retireJs component findings
# ---------------------------------------------------------------------------


def _make_result(parsed_data: dict) -> ToolResult:
    result = MagicMock(spec=ToolResult)
    result.parsed_data = parsed_data
    result.timestamp = "2026-04-12T19:30:00"
    result.output_files = {}
    result.tool_name = "xsstrike"
    return result


class TestXSSTrikeHandlerNormalize:
    def test_xss_finding_normalized(self) -> None:
        parsed = {
            "findings": [{"url": "http://x.com/s", "param": "q", "payload": "<img>"}],
            "component_findings": [],
        }
        rows = XSSTrikeHandler().normalize(_make_result(parsed), "default")
        assert len(rows) == 1
        assert rows[0]["url"] == "http://x.com/s"
        assert rows[0]["severity"] == "high"

    def test_component_finding_normalized(self) -> None:
        parsed = {
            "findings": [],
            "component_findings": [
                {
                    "component_name": "jquery",
                    "component_version": "3.2.1",
                    "cve": "CVE-2019-11358",
                    "severity": "low",
                    "component_location": "http://x.com/jquery.js",
                    "summary": "Object.prototype pollution",
                }
            ],
        }
        rows = XSSTrikeHandler().normalize(_make_result(parsed), "default")
        assert len(rows) == 1
        row = rows[0]
        assert row["package_name"] == "jquery"
        assert row["package_version"] == "3.2.1"
        assert row["vulnerability_id"] == "CVE-2019-11358"
        assert row["severity"] == "low"
        assert row["confidence"] == "confirmed"
        assert row["url"] == "http://x.com/jquery.js"
        assert row["description"] == "Object.prototype pollution"

    def test_mixed_findings_produce_both_rows(self) -> None:
        parsed = {
            "findings": [{"url": "http://x.com/s", "param": "q", "payload": "<img>"}],
            "component_findings": [
                {
                    "component_name": "lodash",
                    "component_version": "4.17.15",
                    "cve": "CVE-2021-23337",
                    "severity": "high",
                    "component_location": "http://x.com/lodash.js",
                }
            ],
        }
        rows = XSSTrikeHandler().normalize(_make_result(parsed), "default")
        assert len(rows) == 2

    def test_component_finding_fingerprint_key(self) -> None:
        finding = {
            "package_name": "jquery",
            "vulnerability_id": "CVE-2019-11358",
            "url": "http://x.com/jquery.js",
        }
        key = XSSTrikeHandler().fingerprint_key(finding)
        assert key == "xsstrike|jquery|CVE-2019-11358|http://x.com/jquery.js"

    def test_xss_finding_fingerprint_key(self) -> None:
        finding = {
            "url": "http://x.com/s",
            "param": "q",
            "payload": "<img>",
        }
        key = XSSTrikeHandler().fingerprint_key(finding)
        assert key == "xsstrike|http://x.com/s|q|<img>"

    def test_component_finding_render_contains_package(self) -> None:
        row = {
            "package_name": "jquery",
            "package_version": "3.2.1",
            "vulnerability_id": "CVE-2019-11358",
            "severity": "low",
            "url": "http://x.com/jquery.js",
        }
        rendered = XSSTrikeHandler().render(row)
        assert "jquery@3.2.1" in rendered
        assert "CVE-2019-11358" in rendered
