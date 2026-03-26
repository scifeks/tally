"""Unit tests for gitleaks handler metadata (no ChromaDB)."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.rag.ingestor import FindingIngestor
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

    def _get_chunks(self, rule_id: str):
        ingestor = FindingIngestor(MagicMock(), "test-proj")
        return ingestor._build_chunks(self._make_gitleaks_result(rule_id), "default")

    def test_known_rule_id_sets_risk_type(self) -> None:
        chunks = self._get_chunks("aws-access-token")
        assert len(chunks) == 1
        assert chunks[0][1]["risk_type"] == "aws-access-token"

    def test_empty_rule_id_omits_risk_type(self) -> None:
        chunks = self._get_chunks("")
        assert len(chunks) == 1
        assert "risk_type" not in chunks[0][1]

    def test_generic_api_key_rule_id_sets_risk_type(self) -> None:
        chunks = self._get_chunks("generic-api-key")
        assert chunks[0][1]["risk_type"] == "generic-api-key"

    def test_jwt_rule_id_sets_risk_type(self) -> None:
        chunks = self._get_chunks("jwt")
        assert chunks[0][1]["risk_type"] == "jwt"

    def test_repo_name_set_when_injected(self) -> None:
        from core.config.schemas import Repository

        repo = Repository.model_construct(
            name="myapp",
            path="/repos/myapp",
            type=["library"],
            docker_path="",
            container_name="",
            languages=["python"],
            base_urls=[],
            test_dirs=[],
        )
        result = self._make_gitleaks_result("aws-access-token")
        assert result.parsed_data is not None
        result.parsed_data["secrets"][0]["file_path"] = "config.py"
        ingestor = FindingIngestor(
            MagicMock(), "test-proj", repositories=[repo], repo_name="myapp"
        )
        chunks = ingestor._build_chunks(result, "default")
        assert len(chunks) == 1
        assert chunks[0][1]["repo"] == "myapp"

    def test_no_title_without_repo(self) -> None:
        chunks = self._get_chunks("aws-access-token")
        assert len(chunks) == 1
        assert "title" not in chunks[0][1]

    def test_no_title_when_no_rule_id(self) -> None:
        chunks = self._get_chunks("")
        assert len(chunks) == 1
        assert "title" not in chunks[0][1]
