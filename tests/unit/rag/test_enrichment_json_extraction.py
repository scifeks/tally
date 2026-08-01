"""Unit tests for _extract_json_object in enrichment pipeline."""

from __future__ import annotations

import json

import pytest

from application.rag.enrichment import _extract_json_object


class TestExtractJsonObject:
    def test_plain_json(self) -> None:
        result = _extract_json_object('{"risk_type": "injection"}')
        assert result == {"risk_type": "injection"}

    def test_json_with_whitespace(self) -> None:
        result = _extract_json_object('  \n {"risk_type": "xss"} \n  ')
        assert result == {"risk_type": "xss"}

    def test_code_fenced_json(self) -> None:
        text = '```json\n{"remediation": "update"}\n```'
        result = _extract_json_object(text)
        assert result == {"remediation": "update"}

    def test_code_fenced_no_language_tag(self) -> None:
        text = '```\n{"risk_type": "ssrf"}\n```'
        result = _extract_json_object(text)
        assert result == {"risk_type": "ssrf"}

    def test_json_with_leading_prose(self) -> None:
        text = 'Here is the classification:\n{"risk_type": "broken_auth"}'
        result = _extract_json_object(text)
        assert result == {"risk_type": "broken_auth"}

    def test_no_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _extract_json_object("no json here at all")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _extract_json_object("")

    @pytest.mark.parametrize(
        "text,expected",
        [
            (
                'Sure thing!\n```json\n{"a": 1}\n```\n',
                {"a": 1},
            ),
            (
                'Result: {"b": 2} done',
                {"b": 2},
            ),
        ],
        ids=["fenced-with-preamble", "inline-with-suffix"],
    )
    def test_various_wrappings(self, text: str, expected: dict) -> None:
        result = _extract_json_object(text)
        assert result == expected
