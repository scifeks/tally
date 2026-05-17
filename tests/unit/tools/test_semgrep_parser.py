"""Tests for semgrep parser and trace extraction."""

import json
from pathlib import Path

from infrastructure.tools.parsers.semgrep import (
    parse_semgrep_json,
    parse_semgrep_json_string,
)
from infrastructure.tools.parsers.semgrep_traces import (
    merge_traces,
    parse_traces,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


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


# -- confidence normalization --


def test_confidence_high_maps_to_confirmed() -> None:
    result = parse_semgrep_json_string(
        _make_semgrep_json("HIGH"),
    )
    assert _confidence(result) == "confirmed"


def test_confidence_medium_maps_to_probable() -> None:
    result = parse_semgrep_json_string(
        _make_semgrep_json("MEDIUM"),
    )
    assert _confidence(result) == "probable"


def test_confidence_low_maps_to_potential() -> None:
    result = parse_semgrep_json_string(
        _make_semgrep_json("LOW"),
    )
    assert _confidence(result) == "potential"


def test_confidence_unknown_yields_none() -> None:
    result = parse_semgrep_json_string(
        _make_semgrep_json("VERY_HIGH"),
    )
    assert _confidence(result) is None


def test_confidence_absent_yields_none() -> None:
    result = parse_semgrep_json_string(_make_semgrep_json())
    assert _confidence(result) is None


# -- text trace parsing --


def _trace_fixture() -> str:
    path = _FIXTURES / "semgrep_taint_traces.txt"
    return path.read_text(encoding="utf-8")


def test_parse_traces_extracts_taint_finding() -> None:
    traces = parse_traces(_trace_fixture())
    assert len(traces) == 1

    t = traces[0]
    assert t["rule_id"] == ("php.lang.security.injection.tainted-exec.tainted-exec")
    assert t["file_path"] == "src/HealthController.php"
    assert t["source_line"] == 84
    assert "file_get_contents" in t["source_content"]
    assert t["sink_line"] == 88
    assert "exec" in t["sink_content"]


def test_parse_traces_extracts_intermediates() -> None:
    traces = parse_traces(_trace_fixture())
    t = traces[0]

    ints = t["intermediates"]
    assert len(ints) == 2
    assert ints[0]["line"] == 84
    assert ints[1]["line"] == 86
    assert "$target" in ints[1]["content"]


def test_parse_traces_skips_non_taint_finding() -> None:
    traces = parse_traces(_trace_fixture())
    rule_ids = [t["rule_id"] for t in traces]
    assert "php.lang.security.exec-use.exec-use" not in rule_ids


def test_parse_traces_empty_input() -> None:
    assert parse_traces("") == []


def test_parse_traces_no_taint_sections() -> None:
    text = """\

    src/app.py
   ❯❯❱ some.rule.id
          Some message

           10┆ some_code()
"""
    assert parse_traces(text) == []


# -- trace merging --


def test_merge_traces_enriches_matching_finding() -> None:
    findings = [
        {
            "rule_id": ("php.lang.security.injection.tainted-exec.tainted-exec"),
            "file_path": "src/HealthController.php",
            "line_start": 88,
            "severity": "medium",
        }
    ]
    traces = parse_traces(_trace_fixture())
    merge_traces(findings, traces)

    f = findings[0]
    assert f["sast_source_line"] == 84
    assert "file_get_contents" in f["sast_source_object"]
    assert "exec" in f["sast_sink_object"]
    assert len(f["dataflow_trace"]) == 2


def test_merge_traces_skips_unmatched_finding() -> None:
    findings = [
        {
            "rule_id": "unrelated.rule",
            "file_path": "other.py",
            "line_start": 1,
        }
    ]
    traces = parse_traces(_trace_fixture())
    merge_traces(findings, traces)

    assert "sast_source_line" not in findings[0]


def test_merge_does_not_create_new_findings() -> None:
    findings: list[dict] = []
    traces = parse_traces(_trace_fixture())
    merge_traces(findings, traces)
    assert len(findings) == 0


# -- full pipeline: JSON parse + trace merge --


def test_json_findings_enriched_with_traces() -> None:
    parsed = parse_semgrep_json(
        _FIXTURES / "semgrep_taint_finding.json",
    )
    traces = parse_traces(_trace_fixture())
    merge_traces(parsed["findings"], traces)

    taint = parsed["findings"][0]
    assert taint["sast_source_line"] == 84
    assert taint["sast_sink_object"] is not None

    pattern_only = parsed["findings"][1]
    assert "sast_source_line" not in pattern_only

    assert parsed["summary"]["total_findings"] == 2
