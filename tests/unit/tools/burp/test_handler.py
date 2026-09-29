"""Unit tests for BurpHandler normalization."""

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.burp import BurpHandler, parse_burp_issue_events

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "tools" / "burp"


def _make_tool_result(
    issue_events: list[dict[str, Any]],
) -> ToolResult:
    parsed = parse_burp_issue_events(issue_events)
    return ToolResult(
        tool_name="burp",
        success=True,
        output="",
        parsed_data=parsed,
        output_files={},
        timestamp="2026-08-25T10:00:00+00:00",
        duration_seconds=5.0,
        finding_count=parsed["summary"]["total_findings"],
    )


def _load_fixture(name: str) -> dict:
    with open(_FIXTURES / name) as f:
        return json.load(f)


class TestBurpHandler:
    def setup_method(self) -> None:
        self.handler = BurpHandler()

    def test_class_attributes(self) -> None:
        assert self.handler.tool_name == "burp"
        assert self.handler.domain == "web"
        assert self.handler.segment == "web"
        assert self.handler.should_enrich is True

    def test_normalize_csrf_finding(self) -> None:
        event = _load_fixture("issue_event_csrf.json")
        result = _make_tool_result([event])
        rows = self.handler.normalize(result, "default")
        assert len(rows) == 1
        row = rows[0]
        assert row["tool"] == "burp"
        assert row["profile"] == "default"
        assert row["severity"] == "medium"
        assert row["confidence"] == "probable"
        assert row["url"] == "https://goat.justinc.app/WebGoat/login"
        assert row["method"] == ""
        assert row["alert_name"] == "Cross-site request forgery"
        assert row["domain"] == "web"
        assert row["segment"] == "web"
        assert row["finding_type"] == json.dumps(["vulnerability"])

    def test_normalize_empty_findings(self) -> None:
        result = _make_tool_result([])
        rows = self.handler.normalize(result, "default")
        assert rows == []

    def test_render_produces_readable_output(self) -> None:
        row = {
            "alert_name": "SQL Injection",
            "url": "https://example.com/api",
            "severity": "high",
            "confidence": "confirmed",
            "description": "Unescaped input.",
        }
        rendered = self.handler.render(row)
        assert "[burp]" in rendered
        assert "SQL Injection" in rendered
        assert "https://example.com/api" in rendered
        assert "high" in rendered

    def test_fingerprint_key_unique_per_finding(self) -> None:
        finding_a = {
            "url": "https://a.com/x",
            "alert_name": "XSS",
            "fingerprint_type": "REFLECTED_XSS",
        }
        finding_b = {
            "url": "https://a.com/y",
            "alert_name": "XSS",
            "fingerprint_type": "REFLECTED_XSS",
        }
        key_a = self.handler.fingerprint_key(finding_a)
        key_b = self.handler.fingerprint_key(finding_b)
        assert key_a != key_b

    def test_fingerprint_key_stable(self) -> None:
        finding = {
            "url": "https://a.com/x",
            "alert_name": "XSS",
            "fingerprint_type": "REFLECTED_XSS",
        }
        assert self.handler.fingerprint_key(finding) == self.handler.fingerprint_key(
            finding
        )
