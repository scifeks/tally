"""Unit tests for web segment validation relaxation (P1)."""

from __future__ import annotations

from typing import Any

import pytest

from application.mcp.finding_payload import (
    FindingPayloadError,
    validate_finding_payload,
)
from application.pipeline.fingerprint import compute_fingerprint


def _valid_web_payload() -> dict[str, Any]:
    """Return a valid web segment payload without file/line_number."""
    return {
        "segment": "web",
        "description": "Reflected XSS in search parameter.",
        "severity": "high",
        "confidence": "confirmed",
        "cwe": ["CWE-79"],
        "finding_type": ["vulnerability"],
        "rule_id": "xss.reflected",
        "meta": {
            "title": "Reflected XSS",
            "owasp_name": "Cross-Site Scripting",
            "remediation": "Encode output and validate input.",
        },
    }


class TestWebSegmentValidation:
    def test_accepts_missing_file_and_line(self) -> None:
        result = validate_finding_payload(_valid_web_payload())
        assert result["file"] is None
        assert result["line_number"] is None
        assert result["segment"] == "web"

    def test_accepts_provided_file_and_line(self) -> None:
        payload = _valid_web_payload()
        payload["file"] = "src/handler.py"
        payload["line_number"] = 42
        result = validate_finding_payload(payload)
        assert result["file"] == "src/handler.py"
        assert result["line_number"] == 42

    def test_sast_segment_rejects_missing_file(self) -> None:
        payload = _valid_web_payload()
        payload["segment"] = "sast"
        with pytest.raises(FindingPayloadError, match="file"):
            validate_finding_payload(payload)

    def test_sast_segment_rejects_missing_line(self) -> None:
        payload = _valid_web_payload()
        payload["segment"] = "sast"
        payload["file"] = "src/handler.py"
        with pytest.raises(FindingPayloadError, match="line"):
            validate_finding_payload(payload)

    def test_no_segment_rejects_missing_file(self) -> None:
        payload = _valid_web_payload()
        del payload["segment"]
        with pytest.raises(FindingPayloadError, match="file"):
            validate_finding_payload(payload)


class TestWebSegmentFingerprint:
    def test_null_file_produces_stable_hash(self) -> None:
        raw_row = {
            "tool": "claudecode",
            "rule_id": "xss.reflected",
            "file_path": None,
            "line_start": None,
        }
        result = compute_fingerprint(raw_row)
        assert isinstance(result, str)
        assert len(result) == 64
