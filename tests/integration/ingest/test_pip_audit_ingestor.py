"""Integration tests for PipAuditHandler.normalize() and render()."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.pip_audit_parser import (  # noqa: E402
    parse_pip_audit_json,
)

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
_TIMESTAMP = "2024-01-01T00:00:00"


def _parse_fixture(filename: str) -> dict:
    return parse_pip_audit_json(_FIXTURES / filename)


def _make_pip_audit_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="pip-audit",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@pytest.fixture()
def vulns_parsed_data() -> dict:
    return _parse_fixture("pip_audit_vulns.json")


@pytest.fixture()
def no_vulns_parsed_data() -> dict:
    return _parse_fixture("pip_audit_no_vulns.json")


class TestPipAuditIngestor:
    def test_count_matches_vulnerabilities(self, vulns_parsed_data: dict) -> None:
        """Row count matches number of vulnerabilities in fixture."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        n_vulns = len(vulns_parsed_data["vulnerabilities"])
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == n_vulns

    def test_zero_vulns_ingests_nothing(self, no_vulns_parsed_data: dict) -> None:
        """0 vulnerabilities → 0 rows, no error."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(no_vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert rows == []

    def test_metadata_fields_always_present(self, vulns_parsed_data: dict) -> None:
        """All required fields are present on every row."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        required = {
            "tool",
            "profile",
            "finding_type",
            "severity",
            "package_name",
            "package_version",
            "vulnerability_id",
            "ecosystem",
            "timestamp",
            "source_file",
        }
        for row in rows:
            missing = required - row.keys()
            assert not missing, f"Missing fields: {missing}"

    def test_metadata_field_values(self, vulns_parsed_data: dict) -> None:
        """Row field values match the parsed fixture data."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        fixture_vulns = {
            v["vulnerability_id"]: v for v in vulns_parsed_data["vulnerabilities"]
        }
        for row in rows:
            assert row["tool"] == "pip-audit"
            assert row["profile"] == "test-repo"
            assert row["finding_type"] == '["dependency"]'
            vuln_id = row["vulnerability_id"]
            assert vuln_id in fixture_vulns, f"Unknown vuln_id in row: {vuln_id}"
            expected = fixture_vulns[vuln_id]
            assert row["package_name"] == expected["package_name"]
            assert row["package_version"] == expected["package_version"]
            assert row["severity"] == expected["severity"]
            assert row["ecosystem"] == expected["affected_ecosystem"]

    def test_fixed_version_in_metadata_when_present(
        self, vulns_parsed_data: dict
    ) -> None:
        """fixed_version key is present when the parser produces one."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        requests_rows = [r for r in rows if r["vulnerability_id"] == "PYSEC-2023-74"]
        assert len(requests_rows) == 1
        assert "fixed_version" in requests_rows[0], (
            "fixed_version must be present when parser produces a non-None value"
        )
        assert requests_rows[0]["fixed_version"] == "2.31.0"

    def test_fixed_version_absent_from_metadata_when_none(
        self, vulns_parsed_data: dict
    ) -> None:
        """fixed_version key is absent when fix_versions list is empty."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        pillow_rows = [r for r in rows if r["vulnerability_id"] == "PYSEC-2023-175"]
        assert len(pillow_rows) == 1
        assert "fixed_version" not in pillow_rows[0], (
            "fixed_version must be absent when fixed_version is None"
        )

    def test_lockfile_never_in_pip_audit_metadata(
        self, vulns_parsed_data: dict
    ) -> None:
        """'lockfile' key is never added to pip-audit rows."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert "lockfile" not in row, (
                f"'lockfile' key must never appear in pip-audit rows: {row}"
            )

    def test_text_template_with_fixed_version(self, vulns_parsed_data: dict) -> None:
        """Rendered text contains package name and vulnerability id."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        requests_rows = [r for r in rows if r["vulnerability_id"] == "PYSEC-2023-74"]
        assert len(requests_rows) == 1
        text = handler.render(requests_rows[0])
        assert "requests" in text
        assert "PYSEC-2023-74" in text

    def test_text_template_without_fixed_version(self, vulns_parsed_data: dict) -> None:
        """Rendered text contains package name and vulnerability id."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        pillow_rows = [r for r in rows if r["vulnerability_id"] == "PYSEC-2023-175"]
        assert len(pillow_rows) == 1
        text = handler.render(pillow_rows[0])
        assert "pillow" in text
        assert "PYSEC-2023-175" in text

    def test_tool_name_in_text_and_metadata(self, vulns_parsed_data: dict) -> None:
        """Rendered text starts with '[pip-audit]' and row tool is 'pip-audit'."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            text = handler.render(row)
            assert text.startswith("[pip-audit]"), (
                f"Rendered text must start with '[pip-audit]', got: {text[:40]!r}"
            )
            assert row["tool"] == "pip-audit"

    def test_no_duplicates(self, vulns_parsed_data: dict) -> None:
        """normalize() is deterministic — same input produces same count."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows_first = handler.normalize(result, profile="test-repo")
        rows_second = handler.normalize(result, profile="test-repo")
        assert len(rows_first) == len(rows_second)

    def test_two_profiles_independent(self, vulns_parsed_data: dict) -> None:
        """normalize() sets profile field correctly per call."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows_a = handler.normalize(result, profile="profile-a")
        rows_b = handler.normalize(result, profile="profile-b")
        assert all(r["profile"] == "profile-a" for r in rows_a)
        assert all(r["profile"] == "profile-b" for r in rows_b)

    def test_shared_metadata_fields(self, vulns_parsed_data: dict) -> None:
        """pip-audit rows have correct domain/enriched/type_* fields."""
        handler = ToolHandlerFactory.load("pip-audit")
        assert handler is not None
        result = _make_pip_audit_result(vulns_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert row["domain"] == "code"
            assert row["enriched"] is False
            assert row["type_dependency"] is True
            assert row["type_vulnerability"] is True
            assert row["type_secret"] is False
            assert row["type_weakness"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_exposure"] is False
