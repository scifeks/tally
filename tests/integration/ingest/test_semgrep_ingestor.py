"""Integration tests for SemgrepChunkBuilder.normalize() and render()."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
_TIMESTAMP = "2024-01-01T00:00:00"


def _make_semgrep_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="semgrep",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@pytest.fixture()
def findings_parsed_data() -> dict:
    raw = json.loads((_FIXTURES / "semgrep_findings.json").read_text())
    findings = []
    for f in raw["findings"]:
        entry: dict = {
            "rule_id": f["rule_id"],
            "severity": f["severity"],
            "message": f["message"],
            "file_path": f["file_path"],
            "line_start": f["line_start"],
            "line_end": f["line_end"],
            "code_snippet": f["code_snippet"],
            "cwe": f.get("cwe"),
            "owasp": f.get("owasp"),
        }
        findings.append(entry)
    return {"findings": findings, "summary": raw["summary"]}


class TestSemgrepIngestor:
    def test_chunk_count(self, findings_parsed_data: dict) -> None:
        """2 findings in fixture → 2 rows."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == 2

    def test_shared_metadata(self, findings_parsed_data: dict) -> None:
        """Semgrep rows have correct domain/enriched/type_* fields."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert row["domain"] == "code"
            assert row["enriched"] is False
            assert row["type_vulnerability"] is True
            assert row["type_weakness"] is True
            assert row["type_secret"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_exposure"] is False
            assert row["type_dependency"] is False

    def test_metadata_fidelity(self, findings_parsed_data: dict) -> None:
        """Row fields match the fixture data."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == 2
        by_rule = {r["rule_id"]: r for r in rows}
        fixture_by_rule = {f["rule_id"]: f for f in findings_parsed_data["findings"]}
        for rule_id, row in by_rule.items():
            finding = fixture_by_rule[rule_id]
            assert row["tool"] == "semgrep"
            assert row["profile"] == "test-repo"
            assert row["finding_type"] == '["vulnerability"]'
            assert row["file_path"] == finding["file_path"]
            assert row["line_start"] == finding["line_start"]
            assert row["line_end"] == finding["line_end"]
            assert isinstance(row["line_start"], int)
            assert isinstance(row["line_end"], int)
            assert row["severity"] == finding["severity"]

    def test_optional_cwe_owasp_present(self, findings_parsed_data: dict) -> None:
        """First finding has cwe and owasp in row."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        xss_rows = [
            r
            for r in rows
            if r["rule_id"] == "python.flask.security.xss.reflected-xss-taint"
        ]
        assert len(xss_rows) == 1
        row = xss_rows[0]
        assert "cwe" in row
        assert row["cwe"] == "CWE-79"
        assert "owasp" in row
        assert row["owasp"] == "A03:2021"

    def test_optional_cwe_owasp_absent(self, findings_parsed_data: dict) -> None:
        """Second finding (null cwe/owasp) has neither key in row."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        pw_rows = [
            r
            for r in rows
            if r["rule_id"] == "python.lang.security.audit.hardcoded-password"
        ]
        assert len(pw_rows) == 1
        row = pw_rows[0]
        assert "cwe" not in row
        assert "owasp" not in row

    def test_no_none_or_empty_metadata_values(self, findings_parsed_data: dict) -> None:
        """No row value is None or empty string (except source_file)."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            for key, val in row.items():
                assert val is not None, f"None value for key {key!r}"
                if key != "source_file":
                    assert val != "", f"Empty string for key {key!r}"

    def test_return_type_is_list(self, findings_parsed_data: dict) -> None:
        """normalize() returns list[dict] with correct length."""
        handler = ToolHandlerFactory.load("semgrep")
        assert handler is not None
        result = _make_semgrep_result(findings_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert isinstance(rows, list)
        assert len(rows) == 2
        assert all(isinstance(r, dict) for r in rows)
