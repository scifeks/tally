"""Integration tests for ZapChunkBuilder.normalize() and render()."""

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


def _make_zap_result(parsed_data: dict, output_files: dict | None = None) -> ToolResult:
    return ToolResult(
        tool_name="zap",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@pytest.fixture()
def alerts_parsed_data() -> dict:
    raw = json.loads((_FIXTURES / "zap_alerts.json").read_text())
    alerts = []
    for a in raw["alerts"]:
        entry: dict = {
            "alert_name": a["alert_name"],
            "risk": a["risk"],
            "confidence": a["confidence"],
            "description": a["description"],
            "solution": a["solution"],
            "url": a["url"],
            "method": a["method"],
            "param": a.get("param"),
            "evidence": a.get("evidence"),
            "cwe_id": a.get("cwe_id"),
        }
        alerts.append(entry)
    return {"alerts": alerts, "summary": raw["summary"]}


class TestZapIngestor:
    def test_chunk_count(self, alerts_parsed_data: dict) -> None:
        """2 alerts in fixture → 2 rows."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == 2

    def test_shared_metadata(self, alerts_parsed_data: dict) -> None:
        """ZAP rows have domain='web', type_vulnerability=True."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert row["domain"] == "web"
            assert row["enriched"] is False
            assert row["type_vulnerability"] is True
            assert row["type_secret"] is False
            assert row["type_weakness"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_exposure"] is False
            assert row["type_dependency"] is False

    def test_metadata_fidelity(self, alerts_parsed_data: dict) -> None:
        """Row fields match the fixture alert data."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == 2
        by_name = {r["alert_name"]: r for r in rows}
        sql_row = by_name["SQL Injection"]
        assert sql_row["tool"] == "zap"
        assert sql_row["profile"] == "test-repo"
        assert sql_row["finding_type"] == '["vulnerability"]'
        assert sql_row["severity"] == "high"
        assert sql_row["confidence"] == "probable"
        assert sql_row["url"] == "https://example.com/api/users"

    def test_remediation_promoted(self, alerts_parsed_data: dict) -> None:
        """'remediation' key is present and non-empty for all rows."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert "remediation" in row, f"'remediation' missing from {row}"
            assert row["remediation"], "remediation must not be empty"

    def test_description_promoted(self, alerts_parsed_data: dict) -> None:
        """'description' key is present and non-empty for all rows."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert "description" in row, f"'description' missing from {row}"
            assert row["description"], "description must not be empty"

    def test_method_uppercase(self, alerts_parsed_data: dict) -> None:
        """method field is uppercased in row."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        by_name = {r["alert_name"]: r for r in rows}
        assert by_name["SQL Injection"]["method"] == "POST"
        assert by_name["X-Content-Type-Options Header Missing"]["method"] == "GET"

    def test_optional_param_present(self, alerts_parsed_data: dict) -> None:
        """First alert (SQL Injection) has 'param' in row."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        sql_rows = [r for r in rows if r["alert_name"] == "SQL Injection"]
        assert len(sql_rows) == 1
        assert "param" in sql_rows[0]
        assert sql_rows[0]["param"] == "id"

    def test_optional_param_absent(self, alerts_parsed_data: dict) -> None:
        """Second alert (header missing) has no 'param' key in row."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        header_rows = [
            r
            for r in rows
            if r["alert_name"] == "X-Content-Type-Options Header Missing"
        ]
        assert len(header_rows) == 1
        assert "param" not in header_rows[0]

    def test_optional_cwe_id_present(self, alerts_parsed_data: dict) -> None:
        """First alert has cwe_id as int in row."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        sql_rows = [r for r in rows if r["alert_name"] == "SQL Injection"]
        assert len(sql_rows) == 1
        assert "cwe_id" in sql_rows[0]
        assert isinstance(sql_rows[0]["cwe_id"], int)
        assert sql_rows[0]["cwe_id"] == 89

    def test_optional_cwe_id_absent(self, alerts_parsed_data: dict) -> None:
        """Second alert (null cwe_id) has no 'cwe_id' key in row."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        header_rows = [
            r
            for r in rows
            if r["alert_name"] == "X-Content-Type-Options Header Missing"
        ]
        assert len(header_rows) == 1
        assert "cwe_id" not in header_rows[0]

    def test_no_none_or_empty_metadata_values(self, alerts_parsed_data: dict) -> None:
        """No row value is None or empty string (except source_file)."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            for key, val in row.items():
                assert val is not None, f"None value for key {key!r}"
                if key != "source_file":
                    assert val != "", f"Empty string for key {key!r}"

    def test_return_type_is_list(self, alerts_parsed_data: dict) -> None:
        """normalize() returns list[dict] with correct length."""
        handler = ToolHandlerFactory.load("zap")
        assert handler is not None
        result = _make_zap_result(alerts_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert isinstance(rows, list)
        assert len(rows) == 2
        assert all(isinstance(r, dict) for r in rows)
