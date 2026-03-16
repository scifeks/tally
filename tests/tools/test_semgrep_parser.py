"""Tests for semgrep_parser confidence normalization."""

import json

from core.tools.parsers.semgrep_parser import parse_semgrep_json_string


def _make_semgrep_json(confidence: str | None = None) -> str:
    meta: dict = {}
    if confidence is not None:
        meta["confidence"] = confidence
    return json.dumps(
        {
            "results": [
                {
                    "check_id": "test-rule",
                    "path": "app.py",
                    "start": {"line": 1, "col": 1},
                    "end": {"line": 1, "col": 10},
                    "extra": {
                        "severity": "ERROR",
                        "message": "test finding",
                        "lines": "x = 1",
                        "metadata": meta,
                    },
                }
            ]
        }
    )


def _confidence(result: dict) -> str | None:
    return result["findings"][0]["confidence"]


def test_confidence_high_maps_to_confirmed() -> None:
    result = parse_semgrep_json_string(_make_semgrep_json("HIGH"))
    assert _confidence(result) == "confirmed"


def test_confidence_medium_maps_to_probable() -> None:
    result = parse_semgrep_json_string(_make_semgrep_json("MEDIUM"))
    assert _confidence(result) == "probable"


def test_confidence_low_maps_to_potential() -> None:
    result = parse_semgrep_json_string(_make_semgrep_json("LOW"))
    assert _confidence(result) == "potential"


def test_confidence_unknown_yields_none() -> None:
    result = parse_semgrep_json_string(_make_semgrep_json("VERY_HIGH"))
    assert _confidence(result) is None


def test_confidence_absent_yields_none() -> None:
    result = parse_semgrep_json_string(_make_semgrep_json())
    assert _confidence(result) is None
