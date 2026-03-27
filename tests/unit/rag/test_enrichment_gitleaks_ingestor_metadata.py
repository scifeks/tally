"""Unit tests for GitleaksHandler.normalize() metadata."""

from __future__ import annotations

from application.rag.chunks.gitleaks import GitleaksHandler
from domain.tools.base import ToolResult


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

    def test_no_title_field_produced(self) -> None:
        rows = self._get_rows("aws-access-token")
        assert len(rows) == 1
        assert "title" not in rows[0]

    def test_no_title_when_no_rule_id(self) -> None:
        rows = self._get_rows("")
        assert len(rows) == 1
        assert "title" not in rows[0]
