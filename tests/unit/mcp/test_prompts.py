"""Unit tests for mcp.prompts.* render functions."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.prompts import (  # noqa: E402
    api_trace,
    sast_trace,
    sca_trace,
)

_IDS = [1, 2, 3]
_PROJECT = "my-project"

# ---------------------------------------------------------------------------
# sast_trace
# ---------------------------------------------------------------------------


def test_sast_trace_returns_string() -> None:
    result = sast_trace.render(_IDS, _PROJECT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_sast_trace_contains_finding_ids() -> None:
    result = sast_trace.render(_IDS, _PROJECT)
    for fid in _IDS:
        assert str(fid) in result


def test_sast_trace_contains_project() -> None:
    result = sast_trace.render(_IDS, _PROJECT)
    assert _PROJECT in result


def test_sast_trace_key_instructions() -> None:
    result = sast_trace.render(_IDS, _PROJECT)
    assert "get_findings_batch" in result
    assert "abs_path" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result
    assert "call_stack" in result


def test_sast_trace_no_grouping_instructions() -> None:
    result = sast_trace.render(_IDS, _PROJECT)
    assert "group" not in result.lower()


def test_api_trace_no_grouping_instructions() -> None:
    result = api_trace.render(_IDS, _PROJECT)
    assert "group" not in result.lower()


# ---------------------------------------------------------------------------
# api_trace
# ---------------------------------------------------------------------------


def test_api_trace_returns_string() -> None:
    result = api_trace.render(_IDS, _PROJECT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_api_trace_contains_finding_ids() -> None:
    result = api_trace.render(_IDS, _PROJECT)
    for fid in _IDS:
        assert str(fid) in result


def test_api_trace_contains_project() -> None:
    result = api_trace.render(_IDS, _PROJECT)
    assert _PROJECT in result


def test_api_trace_key_instructions() -> None:
    result = api_trace.render(_IDS, _PROJECT)
    assert "get_findings_batch" in result
    assert "repo_path" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result


# ---------------------------------------------------------------------------
# sca_trace
# ---------------------------------------------------------------------------


def test_sca_trace_returns_string() -> None:
    result = sca_trace.render(_IDS, _PROJECT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_sca_trace_contains_finding_ids() -> None:
    result = sca_trace.render(_IDS, _PROJECT)
    for fid in _IDS:
        assert str(fid) in result


def test_sca_trace_contains_project() -> None:
    result = sca_trace.render(_IDS, _PROJECT)
    assert _PROJECT in result


def test_sca_trace_key_instructions() -> None:
    result = sca_trace.render(_IDS, _PROJECT)
    assert "get_findings_batch" in result
    assert "repo_path" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result
