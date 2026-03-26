"""Integration tests for ComposerAuditChunkBuilder.normalize() and render()."""

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


def _make_sca_result(tool_name: str, parsed_data: dict) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files={},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


class TestComposerAuditIngestor:
    @pytest.fixture()
    def composer_parsed_data(self) -> dict:
        raw = json.loads((_FIXTURES / "composer_audit_vulns.json").read_text())
        vulns = []
        for v in raw["vulnerabilities"]:
            entry: dict = {
                "package_name": v["package_name"],
                "package_version": v["package_version"],
                "vulnerability_id": v["vulnerability_id"],
                "severity": v["severity"],
                "summary": v["summary"],
                "affected_ecosystem": v["affected_ecosystem"],
                "fixed_version": v.get("fixed_version"),
                "cvss_score": v.get("cvss_score"),
                "source_file": v.get("source_file") or "",
            }
            vulns.append(entry)
        return {"vulnerabilities": vulns, "summary": raw["summary"]}

    def test_shared_metadata(self, composer_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("composer-audit")
        assert handler is not None
        result = _make_sca_result("composer-audit", composer_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert row["domain"] == "code"
            assert row["enriched"] is False
            assert row["type_dependency"] is True
            assert row["type_vulnerability"] is True

    def test_fixed_version_absent(self, composer_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("composer-audit")
        assert handler is not None
        result = _make_sca_result("composer-audit", composer_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert rows
        row = rows[0]
        assert "fixed_version" not in row

    def test_return_type_is_list(self, composer_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("composer-audit")
        assert handler is not None
        result = _make_sca_result("composer-audit", composer_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert isinstance(rows, list)
        assert len(rows) == len(composer_parsed_data["vulnerabilities"])
        assert all(isinstance(r, dict) for r in rows)
