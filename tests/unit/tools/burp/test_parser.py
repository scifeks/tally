"""Unit tests for Burp REST API issue parser."""

import json
from pathlib import Path

from infrastructure.tools.parsers.burp import parse_burp_issue_events

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "tools" / "burp"


def _load_fixture(name: str) -> dict:
    with open(_FIXTURES / name) as f:
        return json.load(f)


class TestParseBurpIssueEvents:
    def test_csrf_issue_extracts_all_fields(self) -> None:
        event = _load_fixture("issue_event_csrf.json")
        result = parse_burp_issue_events([event])
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["name"] == "Cross-site request forgery"
        assert finding["severity"] == "medium"
        assert finding["confidence"] == "probable"
        assert finding["status"] == "confirmed"
        assert finding["origin"] == "https://goat.justinc.app"
        assert finding["path"] == "/WebGoat/login"
        assert finding["url"] == "https://goat.justinc.app/WebGoat/login"
        assert "CSRF token" in finding["description"]
        assert finding["evidence"] != ""
        assert finding["fingerprint_type"] == "CROSS_SITE_REQUEST_FORGERY"

    def test_xss_issue_high_severity_certain_confidence(self) -> None:
        event = _load_fixture("issue_event_xss.json")
        result = parse_burp_issue_events([event])
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["severity"] == "high"
        assert finding["confidence"] == "confirmed"
        assert finding["status"] == "confirmed"
        assert "<script>" in finding["evidence"]

    def test_info_issue_included_with_informational_severity(self) -> None:
        event = _load_fixture("issue_event_info_only.json")
        result = parse_burp_issue_events([event])
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["severity"] == "informational"
        assert findings[0]["evidence"] == ""

    def test_empty_event_list(self) -> None:
        result = parse_burp_issue_events([])
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_non_issue_found_events_are_skipped(self) -> None:
        events = [
            {"type": "issue_updated", "issue": {"name": "X"}},
            _load_fixture("issue_event_csrf.json"),
        ]
        result = parse_burp_issue_events(events)
        assert len(result["findings"]) == 1

    def test_summary_counts_by_severity(self) -> None:
        events = [
            _load_fixture("issue_event_csrf.json"),
            _load_fixture("issue_event_xss.json"),
            _load_fixture("issue_event_info_only.json"),
        ]
        result = parse_burp_issue_events(events)
        summary = result["summary"]
        assert summary["total_findings"] == 3
        assert summary["by_severity"]["high"] == 1
        assert summary["by_severity"]["medium"] == 1
        assert summary["by_severity"]["informational"] == 1

    def test_malformed_issue_missing_name_skipped(self) -> None:
        events = [{"type": "issue_found", "issue": {}}]
        result = parse_burp_issue_events(events)
        assert result["findings"] == []

    def test_missing_evidence_key_produces_empty_evidence(self) -> None:
        event = {
            "type": "issue_found",
            "issue": {
                "name": "Test Issue",
                "origin": "https://example.com",
                "path": "/test",
                "severity": "low",
                "confidence": "tentative",
                "description": "A test.",
                "remediation": "Fix it.",
                "type_index": 1,
                "serial_number": "9999",
                "fingerprint": ":type=TEST:path=%2Ftest",
            },
        }
        result = parse_burp_issue_events([event])
        assert result["findings"][0]["evidence"] == ""

    def test_false_positive_severity_maps_to_informational(
        self,
    ) -> None:
        event = {
            "type": "issue_found",
            "issue": {
                "name": "FP Test",
                "origin": "https://example.com",
                "path": "/",
                "severity": "false_positive",
                "confidence": "certain",
                "description": "Not real.",
                "remediation": "None.",
                "type_index": 0,
                "serial_number": "0001",
                "fingerprint": ":type=FP:path=%2F",
            },
        }
        result = parse_burp_issue_events([event])
        assert result["findings"][0]["severity"] == "informational"
