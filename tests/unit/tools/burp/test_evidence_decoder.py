"""Unit tests for Burp evidence segment decoding."""

import pytest

from infrastructure.tools.burp.evidence import (
    decode_evidence,
    decode_segment,
)


class TestDecodeSegment:
    @pytest.mark.parametrize(
        "segment,expected",
        [
            (
                {"type": "DataSegment", "data": "aGVsbG8="},
                "hello",
            ),
            (
                {"type": "HighlightSegment", "data": "Zm9vYmFy"},
                "foobar",
            ),
            (
                {"type": "SnipSegment", "length": 2048},
                "[...2048 bytes...]",
            ),
        ],
        ids=["data-segment", "highlight-segment", "snip-segment"],
    )
    def test_known_segment_types(
        self,
        segment: dict,
        expected: str,
    ) -> None:
        assert decode_segment(segment) == expected

    def test_unknown_segment_type_returns_empty(self) -> None:
        assert decode_segment({"type": "FutureSegment", "x": 1}) == ""

    def test_invalid_base64_returns_raw_data(self) -> None:
        result = decode_segment({"type": "DataSegment", "data": "!!!invalid!!!"})
        assert result == "!!!invalid!!!"

    def test_missing_data_key_returns_empty(self) -> None:
        assert decode_segment({"type": "DataSegment"}) == ""


class TestDecodeEvidence:
    def test_concatenates_request_response(self) -> None:
        evidence_list = [
            {
                "type": "FirstOrderEvidence",
                "request_response": {
                    "request": [
                        {"type": "DataSegment", "data": "R0VU"},
                    ],
                    "response": [
                        {"type": "DataSegment", "data": "MjAw"},
                    ],
                },
            }
        ]
        result = decode_evidence(evidence_list)
        assert "GET" in result
        assert "200" in result

    def test_empty_evidence_list(self) -> None:
        assert decode_evidence([]) == ""

    def test_evidence_without_request_response(self) -> None:
        evidence_list = [{"type": "InformationListEvidence", "items": []}]
        result = decode_evidence(evidence_list)
        assert result == ""

    def test_multiple_evidence_entries(self) -> None:
        evidence_list = [
            {
                "type": "FirstOrderEvidence",
                "request_response": {
                    "request": [
                        {"type": "DataSegment", "data": "QUFB"},
                    ],
                    "response": [],
                },
            },
            {
                "type": "DiffableEvidence",
                "request_response": {
                    "request": [
                        {"type": "DataSegment", "data": "QkJC"},
                    ],
                    "response": [
                        {"type": "DataSegment", "data": "Q0ND"},
                    ],
                },
            },
        ]
        result = decode_evidence(evidence_list)
        assert "AAA" in result
        assert "BBB" in result
        assert "CCC" in result
