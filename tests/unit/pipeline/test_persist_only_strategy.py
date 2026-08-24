"""Unit tests for PersistOnlyStrategy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.strategies import PersistOnlyStrategy
from domain.pipeline.events import IngestCompleted


def _event(ids: list[int] | None = None) -> IngestCompleted:
    return IngestCompleted(
        ids=[1, 2] if ids is None else ids,
        failed_tools=[],
        run_id=1,
        project_name="test-proj",
        base_path="/tmp",
    )


class TestPersistOnlyStrategy:
    def test_noop_when_ids_empty(self) -> None:
        indexer = MagicMock()
        strategy = PersistOnlyStrategy(finding_repo=MagicMock(), indexer=indexer)

        strategy.handle(_event(ids=[]))

        indexer.index_findings.assert_not_called()

    def test_never_calls_enrichment_pipeline(self) -> None:
        indexer = MagicMock()
        strategy = PersistOnlyStrategy(finding_repo=MagicMock(), indexer=indexer)
        mock_kb = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.EnrichmentPipeline"
            ) as mock_enrich_cls,
            patch.object(strategy, "_get_knowledge_base", return_value=mock_kb),
        ):
            strategy.handle(_event(ids=[1, 2]))

        mock_enrich_cls.assert_not_called()

    def test_calls_indexer_with_correct_args(self) -> None:
        indexer = MagicMock()
        strategy = PersistOnlyStrategy(finding_repo=MagicMock(), indexer=indexer)
        mock_kb = MagicMock()

        with patch.object(strategy, "_get_knowledge_base", return_value=mock_kb):
            strategy.handle(_event(ids=[3, 4]))

        indexer.index_findings.assert_called_once_with(
            mock_kb, [3, 4], caller_label="PersistOnlyStrategy"
        )

    def test_skips_indexer_when_kb_init_fails(self) -> None:
        indexer = MagicMock()
        strategy = PersistOnlyStrategy(finding_repo=MagicMock(), indexer=indexer)

        with patch.object(
            strategy,
            "_get_knowledge_base",
            side_effect=RuntimeError("kb boom"),
        ):
            strategy.handle(_event(ids=[1, 2]))

        indexer.index_findings.assert_not_called()
