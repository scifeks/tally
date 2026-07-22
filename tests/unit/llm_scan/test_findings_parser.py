"""Tests for LLM findings parser."""

import json

from application.llm_scan.findings_parser import parse_llm_findings


class TestParseLlmFindings:
    def test_parses_valid_json_array(self) -> None:
        raw = json.dumps(
            [
                {
                    "file_path": "src/app.py",
                    "line_number": 42,
                    "description": "SQL injection",
                    "severity": "high",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "sast",
                    "reasoning": "User input concatenated into query",
                    "remediation": "Use parameterized queries",
                }
            ]
        )
        findings, errors = parse_llm_findings(raw)
        assert len(findings) == 1
        assert findings[0].file_path == "src/app.py"
        assert not errors

    def test_handles_code_fenced_json(self) -> None:
        raw = (
            "```json\n"
            '[{"file_path":"a.py","description":"XSS",'
            '"severity":"medium","confidence":"probable",'
            '"finding_type":["vulnerability"],"segment":"web"}]\n```'
        )
        findings, errors = parse_llm_findings(raw)
        assert len(findings) == 1

    def test_rejects_invalid_severity(self) -> None:
        raw = json.dumps(
            [
                {
                    "file_path": "a.py",
                    "description": "test",
                    "severity": "super_critical",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "sast",
                }
            ]
        )
        findings, errors = parse_llm_findings(raw)
        assert len(findings) == 0
        assert len(errors) == 1

    def test_empty_array_returns_empty(self) -> None:
        findings, errors = parse_llm_findings("[]")
        assert findings == []
        assert not errors

    def test_invalid_json_returns_error(self) -> None:
        findings, errors = parse_llm_findings("not json")
        assert findings == []
        assert len(errors) == 1
