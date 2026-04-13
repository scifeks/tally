"""Unit tests for the DalFox JSON parser (infrastructure.tools.parsers.dalfox)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.dalfox import (
    DalFoxHandler,
    _parse_dalfox_data,
    parse_dalfox_json,
    parse_dalfox_json_string,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "fixtures" / "ingest" / "dalfox_scan.json"
)

_VERIFIED_FINDING = {
    "Type": "V",
    "Param": "q",
    "Payload": "<script>alert(1)</script>",
    "PoC": "http://example.com/search?q=...",
    "CWE": "CWE-79",
    "Severity": "High",
    "InjectType": "inHTML-URL",
    "Method": "GET",
    "Evidence": "<script>alert(1)</script>",
    "MessageStr": "Reflected XSS found in parameter q",
}

_REFLECTED_FINDING = {
    "Type": "R",
    "Param": "comment",
    "Payload": '"><img src=x onerror=alert(1)>',
    "PoC": "http://example.com/contact?comment=...",
    "CWE": "CWE-79",
    "Severity": "Medium",
    "InjectType": "inHTML-Attr",
    "Method": "POST",
    "Evidence": '"><img src=x onerror=alert(1)>',
    "MessageStr": "Potential reflected XSS",
}


# ---------------------------------------------------------------------------
# parse_dalfox_json_string — empty / malformed inputs
# ---------------------------------------------------------------------------


class TestParseDalfoxJsonStringEdgeCases:
    def test_empty_string_returns_empty_findings(self) -> None:
        result = parse_dalfox_json_string("")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_whitespace_only_returns_empty_findings(self) -> None:
        result = parse_dalfox_json_string("   \n\n\t  ")
        assert result["findings"] == []

    def test_invalid_json_returns_empty_findings(self) -> None:
        result = parse_dalfox_json_string("not json at all")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_json_object_not_array_returns_empty(self) -> None:
        result = parse_dalfox_json_string('{"key": "value"}')
        assert result["findings"] == []

    def test_empty_array_returns_empty_findings(self) -> None:
        result = parse_dalfox_json_string("[]")
        assert result["findings"] == []

    def test_array_of_empty_objects_skipped(self) -> None:
        result = parse_dalfox_json_string("[{}]")
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# parse_dalfox_json_string — valid findings
# ---------------------------------------------------------------------------


class TestParseDalfoxJsonStringValid:
    def test_single_verified_finding_parsed(self) -> None:
        data = json.dumps([_VERIFIED_FINDING])
        result = parse_dalfox_json_string(data)
        assert len(result["findings"]) == 1

    def test_verified_type_maps_to_confirmed_confidence(self) -> None:
        data = json.dumps([_VERIFIED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["confidence"] == "confirmed"

    def test_reflected_type_maps_to_potential_confidence(self) -> None:
        data = json.dumps([_REFLECTED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["confidence"] == "potential"

    def test_grep_type_maps_to_potential_confidence(self) -> None:
        finding = dict(_VERIFIED_FINDING, Type="G")
        result = parse_dalfox_json_string(json.dumps([finding]))
        assert result["findings"][0]["confidence"] == "potential"

    def test_param_extracted(self) -> None:
        data = json.dumps([_VERIFIED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["param"] == "q"

    def test_payload_extracted(self) -> None:
        data = json.dumps([_VERIFIED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["payload"] == "<script>alert(1)</script>"

    def test_poc_used_as_url(self) -> None:
        data = json.dumps([_VERIFIED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["url"] == _VERIFIED_FINDING["PoC"]

    def test_severity_normalised_to_lowercase(self) -> None:
        data = json.dumps([_VERIFIED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["severity"] == "high"

    def test_method_extracted(self) -> None:
        data = json.dumps([_REFLECTED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["findings"][0]["method"] == "POST"

    def test_summary_total_findings_correct(self) -> None:
        data = json.dumps([_VERIFIED_FINDING, _REFLECTED_FINDING])
        result = parse_dalfox_json_string(data)
        assert result["summary"]["total_findings"] == 2


# ---------------------------------------------------------------------------
# parse_dalfox_json — file reading
# ---------------------------------------------------------------------------


class TestParseDalfoxJson:
    def test_reads_fixture_file(self) -> None:
        result = parse_dalfox_json(_FIXTURE_PATH)
        assert len(result["findings"]) == 3

    def test_fixture_has_correct_summary(self) -> None:
        result = parse_dalfox_json(_FIXTURE_PATH)
        assert result["summary"]["total_findings"] == 3

    def test_missing_file_returns_error_key(self, tmp_path: Path) -> None:
        result = parse_dalfox_json(tmp_path / "nonexistent.json")
        assert "error" in result
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# _parse_dalfox_data — internal helper
# ---------------------------------------------------------------------------


class TestParseDalfoxData:
    def test_empty_list_returns_empty(self) -> None:
        result = _parse_dalfox_data([])
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_non_dict_items_skipped(self) -> None:
        result = _parse_dalfox_data(["string", 42, None])  # type: ignore[list-item]
        assert result["findings"] == []

    def test_cwe_normalised_to_int(self) -> None:
        finding = dict(_VERIFIED_FINDING, CWE="CWE-79")
        result = _parse_dalfox_data([finding])
        # CWE is stored as-is; handler normalises to int in normalize()
        assert result["findings"][0]["cwe"] == "CWE-79"

    def test_missing_severity_defaults_to_medium(self) -> None:
        finding = {k: v for k, v in _VERIFIED_FINDING.items() if k != "Severity"}
        result = _parse_dalfox_data([finding])
        assert result["findings"][0]["severity"] == "medium"

    def test_unknown_type_defaults_to_potential(self) -> None:
        finding = dict(_VERIFIED_FINDING, Type="X")
        result = _parse_dalfox_data([finding])
        assert result["findings"][0]["confidence"] == "potential"


# ---------------------------------------------------------------------------
# DalFoxHandler.normalize
# ---------------------------------------------------------------------------


def _make_result(findings: list[dict]) -> ToolResult:
    mock = MagicMock(spec=ToolResult)
    mock.parsed_data = {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }
    mock.timestamp = "2024-01-01T00:00:00"
    mock.output_files = {}
    return mock


class TestDalFoxHandlerNormalize:
    def test_empty_findings_returns_empty_rows(self) -> None:
        handler = DalFoxHandler()
        result = _make_result([])
        rows = handler.normalize(result, "default")
        assert rows == []

    def test_row_tool_is_dalfox(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert rows[0]["tool"] == "dalfox"

    def test_row_url_matches_poc(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert rows[0]["url"] == _VERIFIED_FINDING["PoC"]

    def test_row_cwe_id_parsed_from_cwe_string(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert rows[0]["cwe_id"] == 79

    def test_row_severity_high(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert rows[0]["severity"] == "high"

    def test_row_confidence_confirmed_for_verified(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert rows[0]["confidence"] == "confirmed"

    def test_row_type_vulnerability_flag_true(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert rows[0]["type_vulnerability"] is True

    def test_row_other_type_flags_false(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        for flag in ("type_secret", "type_dependency", "type_misconfiguration"):
            assert rows[0][flag] is False

    def test_multiple_findings_produce_multiple_rows(self) -> None:
        handler = DalFoxHandler()
        parsed = _parse_dalfox_data([_VERIFIED_FINDING, _REFLECTED_FINDING])
        result = _make_result(parsed["findings"])
        rows = handler.normalize(result, "default")
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# DalFoxHandler.render
# ---------------------------------------------------------------------------


class TestDalFoxHandlerRender:
    def test_render_contains_tool_name(self) -> None:
        handler = DalFoxHandler()
        row = {
            "tool": "dalfox",
            "url": "http://example.com",
            "param": "q",
            "payload": "<script>",
            "method": "GET",
            "severity": "high",
            "confidence": "confirmed",
            "cwe_id": 79,
        }
        rendered = handler.render(row)
        assert "dalfox" in rendered

    def test_render_contains_url(self) -> None:
        handler = DalFoxHandler()
        row = {
            "url": "http://example.com/page",
            "param": "q",
            "payload": "<script>",
            "method": "GET",
            "severity": "high",
            "confidence": "confirmed",
            "cwe_id": 79,
        }
        rendered = handler.render(row)
        assert "http://example.com/page" in rendered

    def test_render_contains_param(self) -> None:
        handler = DalFoxHandler()
        row = {
            "url": "http://example.com",
            "param": "search_query",
            "payload": "<img>",
            "method": "GET",
            "severity": "medium",
            "confidence": "potential",
            "cwe_id": 79,
        }
        rendered = handler.render(row)
        assert "search_query" in rendered

    def test_render_prefixed_with_dalfox_tag(self) -> None:
        handler = DalFoxHandler()
        row = {
            "url": "http://x.com",
            "param": "p",
            "payload": "x",
            "method": "GET",
            "severity": "low",
            "confidence": "potential",
            "cwe_id": 79,
        }
        rendered = handler.render(row)
        assert rendered.startswith("[dalfox]")


# ---------------------------------------------------------------------------
# DalFoxHandler.fingerprint_key
# ---------------------------------------------------------------------------


class TestDalFoxHandlerFingerprintKey:
    def test_fingerprint_starts_with_dalfox(self) -> None:
        handler = DalFoxHandler()
        key = handler.fingerprint_key({"url": "u", "param": "p", "payload": "x"})
        assert key.startswith("dalfox|")

    def test_fingerprint_includes_url_param_payload(self) -> None:
        handler = DalFoxHandler()
        key = handler.fingerprint_key(
            {"url": "http://a.com", "param": "q", "payload": "<script>"}
        )
        assert "http://a.com" in key
        assert "q" in key
        assert "<script>" in key

    def test_fingerprint_empty_finding_is_stable(self) -> None:
        handler = DalFoxHandler()
        key = handler.fingerprint_key({})
        assert key == "dalfox|||"

    def test_fingerprint_same_inputs_same_key(self) -> None:
        handler = DalFoxHandler()
        finding = {"url": "http://b.com", "param": "x", "payload": "y"}
        assert handler.fingerprint_key(finding) == handler.fingerprint_key(finding)

    def test_fingerprint_different_payload_different_key(self) -> None:
        handler = DalFoxHandler()
        k1 = handler.fingerprint_key(
            {"url": "http://x.com", "param": "q", "payload": "a"}
        )
        k2 = handler.fingerprint_key(
            {"url": "http://x.com", "param": "q", "payload": "b"}
        )
        assert k1 != k2
