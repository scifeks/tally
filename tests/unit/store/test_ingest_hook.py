"""Unit tests for EnrichmentPipeline SQLite ingest hook."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.rag.enrichment import EnrichmentPipeline


class TestIngestHook:
    def test_hook_fires_after_enrich(self) -> None:
        """upsert_findings is called after enrich() completes."""
        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "test finding text",
            "metadata": {"tool": "gitleaks", "severity": "high"},
        }
        mock_repo = MagicMock()
        pipeline = EnrichmentPipeline(
            mock_engine,
            finding_repo=mock_repo,
            run_id=42,
            llm_provider=MagicMock(),
        )
        pipeline._call_llm_worker = MagicMock(return_value={})  # type: ignore[method-assign]

        pipeline.enrich(["doc1"])

        mock_repo.upsert_findings.assert_called_once_with(
            42, [{"tool": "gitleaks", "severity": "high"}]
        )

    def test_hook_fires_with_multiple_docs(self) -> None:
        mock_engine = MagicMock()
        mock_engine.get_document_by_id.side_effect = lambda doc_id: {
            "id": doc_id,
            "document": "text",
            "metadata": {"tool": "semgrep", "rule_id": doc_id},
        }
        mock_repo = MagicMock()
        pipeline = EnrichmentPipeline(
            mock_engine,
            finding_repo=mock_repo,
            run_id=7,
            llm_provider=MagicMock(),
        )
        pipeline._call_llm_worker = MagicMock(return_value={})  # type: ignore[method-assign]

        pipeline.enrich(["d1", "d2", "d3"])

        call_args = mock_repo.upsert_findings.call_args
        assert call_args[0][0] == 7  # run_id
        findings = call_args[0][1]
        assert len(findings) == 3

    def test_hook_not_called_when_no_repo(self) -> None:
        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "text",
            "metadata": {"tool": "nmap"},
        }
        pipeline = EnrichmentPipeline(mock_engine)

        # Should not raise even without repo; nmap provides all fields so no LLM call
        pipeline.enrich(["doc1"])

    def test_hook_failure_does_not_raise(self) -> None:
        """SQLite failure in the hook must not interrupt the scan."""
        mock_engine = MagicMock()
        mock_engine.get_document_by_id.return_value = {
            "id": "doc1",
            "document": "text",
            "metadata": {"tool": "gitleaks"},
        }
        mock_repo = MagicMock()
        mock_repo.upsert_findings.side_effect = RuntimeError("DB locked")
        pipeline = EnrichmentPipeline(
            mock_engine,
            finding_repo=mock_repo,
            run_id=1,
            llm_provider=MagicMock(),
        )
        pipeline._call_llm_worker = MagicMock(return_value={})  # type: ignore[method-assign]

        # Must not raise
        pipeline.enrich(["doc1"])
