"""Unit tests for EnrichmentPipeline SQLite write-back via update_enrichment_fields."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.rag.enrichment import EnrichmentPipeline
from domain.findings.normalization import split_enrichment_fields


def _make_pipeline(
    finding_repo: MagicMock, llm_provider: MagicMock
) -> EnrichmentPipeline:
    return EnrichmentPipeline(
        finding_repo=finding_repo,
        run_id=1,
        llm_provider=llm_provider,
    )


def _row(row_id: int, tool: str = "semgrep", enriched: bool = False) -> dict:
    return {"id": row_id, "tool": tool, "enriched": enriched, "severity": "high"}


class TestEnrichmentWriteBack:
    def test_update_enrichment_fields_called_after_enrich(self) -> None:
        """update_enrichment_fields is called for each enriched finding."""
        mock_repo = MagicMock()
        mock_repo.get_by_ids.return_value = [_row(1, tool="semgrep")]
        mock_llm = MagicMock()
        pipeline = _make_pipeline(mock_repo, mock_llm)
        pipeline._call_llm_worker = MagicMock(return_value={"risk_type": "xss"})  # type: ignore[method-assign]

        pipeline.enrich([1])

        cols, meta = split_enrichment_fields({"risk_type": "xss"})
        mock_repo.update_enrichment_fields.assert_called_once_with(
            1, cols, meta, source="llm_inference"
        )

    def test_update_called_for_each_finding(self) -> None:
        """update_enrichment_fields is called once per enriched finding."""
        mock_repo = MagicMock()
        mock_repo.get_by_ids.return_value = [
            _row(1, tool="semgrep"),
            _row(2, tool="semgrep"),
            _row(3, tool="semgrep"),
        ]
        mock_llm = MagicMock()
        pipeline = _make_pipeline(mock_repo, mock_llm)
        pipeline._call_llm_worker = MagicMock(return_value={"risk_type": "xss"})  # type: ignore[method-assign]

        pipeline.enrich([1, 2, 3])

        assert mock_repo.update_enrichment_fields.call_count == 3

    def test_no_llm_call_for_non_enriching_tool(self) -> None:
        """Tools with should_enrich=False (nmap, gitleaks) get no LLM call."""
        mock_repo = MagicMock()
        mock_repo.get_by_ids.return_value = [_row(1, tool="nmap")]
        mock_llm = MagicMock()
        pipeline = _make_pipeline(mock_repo, mock_llm)

        pipeline.enrich([1])

        mock_llm.complete.assert_not_called()
        mock_repo.update_enrichment_fields.assert_not_called()

    def test_already_enriched_row_skipped(self) -> None:
        """Rows with enriched=True are not sent to LLM or written back."""
        mock_repo = MagicMock()
        mock_repo.get_by_ids.return_value = [_row(1, tool="semgrep", enriched=True)]
        mock_llm = MagicMock()
        pipeline = _make_pipeline(mock_repo, mock_llm)

        pipeline.enrich([1])

        mock_llm.complete.assert_not_called()
        mock_repo.update_enrichment_fields.assert_not_called()

    def test_empty_ids_no_db_call(self) -> None:
        """enrich([]) makes no repository calls."""
        mock_repo = MagicMock()
        mock_llm = MagicMock()
        pipeline = _make_pipeline(mock_repo, mock_llm)

        pipeline.enrich([])

        mock_repo.get_by_ids.assert_not_called()
        mock_repo.update_enrichment_fields.assert_not_called()

    def test_llm_failure_does_not_raise(self) -> None:
        """A total LLM failure for one finding must not crash the pipeline."""
        mock_repo = MagicMock()
        mock_repo.get_by_ids.return_value = [_row(1, tool="semgrep")]
        mock_llm = MagicMock()
        pipeline = _make_pipeline(mock_repo, mock_llm)
        pipeline._call_llm_worker = MagicMock(side_effect=RuntimeError("LLM down"))  # type: ignore[method-assign]

        pipeline.enrich([1])

        mock_repo.update_enrichment_fields.assert_not_called()
        assert pipeline.had_errors is True
