"""Unit tests for mcp.prompts.* render functions."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from tally_mcp.prompts import (  # noqa: E402
    api_trace,
    code_trace,
    dependency,
    enrich_only,
)

_IDS = [1, 2, 3]
_PROJECT = "my-project"

# ---------------------------------------------------------------------------
# code_trace
# ---------------------------------------------------------------------------


def test_code_trace_returns_string() -> None:
    result = code_trace.render(_IDS, _PROJECT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_code_trace_contains_finding_ids() -> None:
    result = code_trace.render(_IDS, _PROJECT)
    for fid in _IDS:
        assert str(fid) in result


def test_code_trace_contains_project() -> None:
    result = code_trace.render(_IDS, _PROJECT)
    assert _PROJECT in result


def test_code_trace_key_instructions() -> None:
    result = code_trace.render(_IDS, _PROJECT)
    assert "get_findings_batch" in result
    assert "get_project_config" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result
    assert "call_stack" in result


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
    assert "get_project_config" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result


# ---------------------------------------------------------------------------
# dependency
# ---------------------------------------------------------------------------


def test_dependency_returns_string() -> None:
    result = dependency.render(_IDS, _PROJECT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_dependency_contains_finding_ids() -> None:
    result = dependency.render(_IDS, _PROJECT)
    for fid in _IDS:
        assert str(fid) in result


def test_dependency_contains_project() -> None:
    result = dependency.render(_IDS, _PROJECT)
    assert _PROJECT in result


def test_dependency_key_instructions() -> None:
    result = dependency.render(_IDS, _PROJECT)
    assert "get_findings_batch" in result
    assert "get_project_config" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result


# ---------------------------------------------------------------------------
# enrich_only
# ---------------------------------------------------------------------------


def test_enrich_only_returns_string() -> None:
    result = enrich_only.render(_IDS, _PROJECT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_enrich_only_contains_finding_ids() -> None:
    result = enrich_only.render(_IDS, _PROJECT)
    for fid in _IDS:
        assert str(fid) in result


def test_enrich_only_contains_project() -> None:
    result = enrich_only.render(_IDS, _PROJECT)
    assert _PROJECT in result


def test_enrich_only_key_instructions() -> None:
    result = enrich_only.render(_IDS, _PROJECT)
    assert "get_findings_batch" in result
    assert "update_findings_batch" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert "remediation" in result
    assert "confirmed" in result
