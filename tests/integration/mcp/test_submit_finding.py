"""Integration tests for McpIngestService.submit_finding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from application.mcp.ingest_service import McpIngestService
from application.rag.finding_indexer import FindingIndexer
from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import Repository
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def run_id(run_repo: RunRepository) -> int:
    return run_repo.create(
        project_id=1,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
    )


@pytest.fixture()
def repo_repo(factory: ConnectionFactory) -> RepositoryRepository:
    return RepositoryRepository(factory)


@pytest.fixture()
def active_repo_id(repo_repo: RepositoryRepository, tmp_path: Path) -> int:
    return repo_repo.insert(
        Repository(
            name="api",
            path=str(tmp_path),
            services=[RepoService(name="default", type=["api"], languages=["python"])],
        )
    )


@pytest.fixture()
def indexer(finding_repo: FindingRepository) -> FindingIndexer:
    return FindingIndexer(finding_repo)


@pytest.fixture()
def mock_kb() -> Mock:
    kb = Mock()
    kb.add_findings = Mock()
    return kb


def _assert_rejected_without_insert(
    result: dict,
    finding_repo: FindingRepository,
    run_id: int,
    repo_id: int,
) -> None:
    assert result == {
        "finding_id": None,
        "status": "rejected",
        "error": f"repo_id {repo_id} is not an active repository in this project",
    }
    assert finding_repo.get_findings_by_run_id(run_id) == []


def _valid_payload() -> dict:
    return {
        "file": "src/db.py",
        "line_number": 42,
        "description": "SQL query built from user input via string concat.",
        "severity": "critical",
        "confidence": "confirmed",
        "cwe": ["CWE-89"],
        "finding_type": ["vulnerability"],
        "rule_id": "injection.sql",
        "meta": {
            "title": "SQL Injection in User Lookup",
            "owasp_name": "Injection",
            "remediation": "Use parameterized queries with sqlite3 placeholders.",
        },
    }


class TestSubmitFindingHappyPath:
    def test_returns_accepted_with_finding_id(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "accepted"
        assert isinstance(result["finding_id"], int)
        assert result["finding_id"] > 0

    def test_persists_finding_in_database(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding_id = result["finding_id"]
        finding = finding_repo.get_finding(finding_id)
        assert finding is not None

    def test_sets_tool_to_claudecode(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.tool == "claudecode"

    def test_sets_domain_to_llm(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.domain == "llm"

    def test_sets_segment_to_default_sast(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.segment == "sast"

    def test_respects_custom_segment(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        payload["segment"] = "web"
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.segment == "web"

    def test_sets_status_to_active(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.status == "active"

    def test_sets_severity_from_payload(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.severity == "critical"

    def test_marks_should_report_true(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.should_report is True

    def test_stores_meta_fields(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.meta["title"] == "SQL Injection in User Lookup"
        assert finding.meta["owasp_name"] == "Injection"


class TestSubmitFindingValidation:
    def test_rejects_missing_description(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        del payload["description"]
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "rejected"
        assert result["finding_id"] is None
        assert "description" in result["error"]

    def test_rejects_invalid_severity(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        payload["severity"] = "totally_broken"
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "rejected"
        assert result["finding_id"] is None
        assert "severity" in result["error"]

    def test_rejects_missing_file(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        del payload["file"]
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "rejected"
        assert result["finding_id"] is None
        assert "file" in result["error"]

    def test_rejects_missing_cwe(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        del payload["cwe"]
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "rejected"
        assert result["finding_id"] is None
        assert "cwe" in result["error"]

    def test_error_message_is_string(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        del payload["severity"]
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0

    def test_no_row_written_on_validation_error(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )
        payload = _valid_payload()
        del payload["rule_id"]
        rows_before = finding_repo.get_findings_by_run_id(run_id)

        service.submit_finding(run_id, payload, repo_id=None)

        rows_after = finding_repo.get_findings_by_run_id(run_id)
        assert len(rows_after) == len(rows_before)


class TestSubmitFindingMultiple:
    def test_two_findings_with_different_rule_ids(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )

        payload1 = _valid_payload()
        payload1["rule_id"] = "injection.sql"

        payload2 = _valid_payload()
        payload2["rule_id"] = "injection.xpath"

        result1 = service.submit_finding(run_id, payload1, repo_id=None)
        result2 = service.submit_finding(run_id, payload2, repo_id=None)

        assert result1["status"] == "accepted"
        assert result2["status"] == "accepted"
        assert result1["finding_id"] != result2["finding_id"]

        finding1 = finding_repo.get_finding(result1["finding_id"])
        finding2 = finding_repo.get_finding(result2["finding_id"])
        assert finding1 is not None
        assert finding2 is not None

        assert finding1.rule_id == "injection.sql"
        assert finding2.rule_id == "injection.xpath"

    def test_distinct_fingerprints(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=Mock()
        )

        payload1 = _valid_payload()
        payload1["rule_id"] = "rule1"
        payload1["file"] = "src/file1.py"

        payload2 = _valid_payload()
        payload2["rule_id"] = "rule2"
        payload2["file"] = "src/file2.py"

        result1 = service.submit_finding(run_id, payload1, repo_id=None)
        result2 = service.submit_finding(run_id, payload2, repo_id=None)

        finding1 = finding_repo.get_finding(result1["finding_id"])
        finding2 = finding_repo.get_finding(result2["finding_id"])
        assert finding1 is not None
        assert finding2 is not None

        assert finding1.fingerprint != finding2.fingerprint


class TestSubmitFindingIndexing:
    def test_calls_indexer_with_kb_and_ids(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        indexer: FindingIndexer,
        mock_kb: Mock,
    ) -> None:
        mock_indexer = Mock(spec=FindingIndexer)
        service = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
            repo_repo=Mock(),
            indexer=mock_indexer,
            knowledge_base=mock_kb,
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        finding_id = result["finding_id"]
        mock_indexer.index_findings.assert_called_once()
        call_args = mock_indexer.index_findings.call_args
        assert call_args[0][0] == mock_kb
        assert call_args[0][1] == [finding_id]
        assert call_args[1]["caller_label"] == "McpIngestService"

    def test_skips_indexing_when_indexer_not_provided(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        mock_kb: Mock,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
            repo_repo=Mock(),
            indexer=None,
            knowledge_base=mock_kb,
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "accepted"
        assert result["finding_id"] is not None

    def test_skips_indexing_when_kb_not_provided(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        indexer: FindingIndexer,
    ) -> None:
        service = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
            repo_repo=Mock(),
            indexer=indexer,
            knowledge_base=None,
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "accepted"
        assert result["finding_id"] is not None

    def test_handles_indexing_exception_gracefully(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        mock_kb: Mock,
    ) -> None:
        mock_indexer = Mock(spec=FindingIndexer)
        mock_indexer.index_findings.side_effect = RuntimeError(
            "Vector index unavailable"
        )
        service = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
            repo_repo=Mock(),
            indexer=mock_indexer,
            knowledge_base=mock_kb,
        )
        payload = _valid_payload()
        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "accepted"
        assert result["finding_id"] is not None


class TestSubmitFindingRepoId:
    @pytest.fixture()
    def service(
        self,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
        repo_repo: RepositoryRepository,
    ) -> McpIngestService:
        return McpIngestService(
            finding_repo=finding_repo, run_repo=run_repo, repo_repo=repo_repo
        )

    def test_stores_active_repo_id(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        run_id: int,
        active_repo_id: int,
    ) -> None:
        result = service.submit_finding(
            run_id, _valid_payload(), repo_id=active_repo_id
        )

        assert result["status"] == "accepted"
        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.repo_id == active_repo_id

    def test_rejects_unknown_repo_id(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        run_id: int,
        active_repo_id: int,
    ) -> None:
        repo_id = active_repo_id + 1000

        result = service.submit_finding(run_id, _valid_payload(), repo_id=repo_id)

        _assert_rejected_without_insert(result, finding_repo, run_id, repo_id)

    def test_rejects_soft_deleted_repo_id(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        repo_repo: RepositoryRepository,
        run_id: int,
        active_repo_id: int,
    ) -> None:
        repo_repo.soft_delete(active_repo_id)

        result = service.submit_finding(
            run_id, _valid_payload(), repo_id=active_repo_id
        )

        _assert_rejected_without_insert(result, finding_repo, run_id, active_repo_id)

    def test_meta_repo_id_cannot_override_active_repo_id(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        run_id: int,
        active_repo_id: int,
    ) -> None:
        payload = _valid_payload()
        payload["meta"]["repo_id"] = active_repo_id + 1000

        result = service.submit_finding(run_id, payload, repo_id=active_repo_id)

        assert result["status"] == "accepted"
        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.repo_id == active_repo_id

    def test_meta_repo_id_ignored_when_repo_id_is_none(
        self,
        service: McpIngestService,
        finding_repo: FindingRepository,
        run_id: int,
        active_repo_id: int,
    ) -> None:
        payload = _valid_payload()
        payload["meta"]["repo_id"] = active_repo_id + 1000

        result = service.submit_finding(run_id, payload, repo_id=None)

        assert result["status"] == "accepted"
        finding = finding_repo.get_finding(result["finding_id"])
        assert finding is not None
        assert finding.repo_id is None
