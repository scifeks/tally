"""Unit tests for GitleaksHandler.normalize() metadata."""

from __future__ import annotations

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.gitleaks import GitleaksHandler


class TestGitleaksIngestorMetadata:
    def _make_gitleaks_result(self, rule_id: str) -> ToolResult:
        return ToolResult(
            tool_name="gitleaks",
            success=True,
            output="",
            parsed_data={
                "secrets": [
                    {
                        "rule_id": rule_id,
                        "description": "AWS Access Token",
                        "file_path": "config.py",
                        "line_number": 42,
                        "tags": ["aws"],
                        "commit": "abc123",
                        "fingerprint": "fp-001",
                    }
                ],
                "summary": {"total": 1},
            },
            output_files={},
            timestamp="2024-01-01T00:00:00",
            duration_seconds=0.1,
        )

    def _get_rows(self, rule_id: str) -> list[dict]:
        return GitleaksHandler().normalize(
            self._make_gitleaks_result(rule_id), "default"
        )

    def test_known_rule_id_sets_risk_type(self) -> None:
        rows = self._get_rows("aws-access-token")
        assert len(rows) == 1
        assert rows[0]["risk_type"] == "aws-access-token"

    def test_empty_rule_id_omits_risk_type(self) -> None:
        rows = self._get_rows("")
        assert len(rows) == 1
        assert "risk_type" not in rows[0]

    def test_generic_api_key_rule_id_sets_risk_type(self) -> None:
        rows = self._get_rows("generic-api-key")
        assert rows[0]["risk_type"] == "generic-api-key"

    def test_jwt_rule_id_sets_risk_type(self) -> None:
        rows = self._get_rows("jwt")
        assert rows[0]["risk_type"] == "jwt"

    def test_title_field_set_from_rule_id(self) -> None:
        rows = self._get_rows("aws-access-token")
        assert len(rows) == 1
        assert rows[0]["title"] == "aws-access-token"

    def test_no_title_when_no_rule_id(self) -> None:
        rows = self._get_rows("")
        assert len(rows) == 1
        assert "title" not in rows[0]

    def _make_result_with_source(self, source: str) -> ToolResult:
        return ToolResult(
            tool_name="gitleaks",
            success=True,
            output="",
            parsed_data={
                "secrets": [
                    {
                        "rule_id": "aws-access-token",
                        "description": "AWS Access Token",
                        "file_path": "config.py",
                        "line_number": 42,
                        "tags": ["aws"],
                        "commit": None,
                        "fingerprint": "fp-001",
                        "source": source,
                    }
                ],
                "summary": {"total": 1},
            },
            output_files={},
            timestamp="2024-01-01T00:00:00",
            duration_seconds=0.1,
        )

    def test_source_dir_written_to_row(self) -> None:
        rows = GitleaksHandler().normalize(
            self._make_result_with_source("dir"), "default"
        )
        assert len(rows) == 1
        assert rows[0]["source"] == "dir"

    def test_source_git_written_to_row(self) -> None:
        rows = GitleaksHandler().normalize(
            self._make_result_with_source("git"), "default"
        )
        assert len(rows) == 1
        assert rows[0]["source"] == "git"

    def test_missing_source_omitted_from_row(self) -> None:
        """Findings with no source key (e.g. legacy data) produce no source field."""
        rows = self._get_rows("aws-access-token")
        assert "source" not in rows[0]
