"""Unit tests for LLM-based Organizer note enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.tools.burp.note_enrichment import NoteEnrichment


def _provider(response: str) -> MagicMock:
    mock = MagicMock()
    mock.complete.return_value = response
    return mock


class TestClassify:
    def test_valid_response_produces_classification(self) -> None:
        provider = _provider(
            '{"vulnerability_type": "idor", "cwe": "CWE-639", "severity": "high"}'
        )
        result = NoteEnrichment(provider).classify("found an IDOR")

        assert result is not None
        assert result.vulnerability_type == "idor"
        assert result.cwe == "CWE-639"
        assert result.severity == "high"

    def test_tolerates_code_fenced_json(self) -> None:
        provider = _provider(
            '```json\n{"vulnerability_type": "sql_injection",'
            ' "cwe": "CWE-89", "severity": "critical"}\n```'
        )
        result = NoteEnrichment(provider).classify("sqli in login")

        assert result is not None
        assert result.cwe == "CWE-89"
        assert result.severity == "critical"

    def test_empty_note_skips_llm(self) -> None:
        provider = _provider("{}")
        result = NoteEnrichment(provider).classify("   ")

        assert result is None
        provider.complete.assert_not_called()

    @pytest.mark.parametrize(
        ("response", "expected_cwe", "expected_severity"),
        [
            (
                '{"vulnerability_type": "xss", "cwe": "not-a-cwe", "severity": "high"}',
                "CWE-0",
                "high",
            ),
            (
                '{"vulnerability_type": "xss", "cwe": "CWE-79", "severity": "spicy"}',
                "CWE-79",
                "informational",
            ),
            (
                '{"vulnerability_type": "xss"}',
                "CWE-0",
                "informational",
            ),
        ],
        ids=["bad-cwe", "bad-severity", "missing-fields"],
    )
    def test_invalid_fields_fall_back(
        self,
        response: str,
        expected_cwe: str,
        expected_severity: str,
    ) -> None:
        result = NoteEnrichment(_provider(response)).classify("note")

        assert result is not None
        assert result.cwe == expected_cwe
        assert result.severity == expected_severity

    def test_missing_vulnerability_type_falls_back(self) -> None:
        provider = _provider('{"cwe": "CWE-79", "severity": "low"}')
        result = NoteEnrichment(provider).classify("note")

        assert result is not None
        assert result.vulnerability_type == "unclassified"

    def test_unparseable_response_returns_none(self) -> None:
        result = NoteEnrichment(_provider("not json at all")).classify("note")
        assert result is None

    def test_provider_error_returns_none(self) -> None:
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("llm down")
        result = NoteEnrichment(provider).classify("note")
        assert result is None
