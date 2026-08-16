"""Unit tests for EnrichThenPersistStrategy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.strategies import EnrichThenPersistStrategy
from domain.pipeline.events import IngestCompleted


def _event(ids: list[int] | None = None) -> IngestCompleted:
    return IngestCompleted(
        ids=[1, 2] if ids is None else ids,
        failed_tools=[],
        run_id=1,
        project_name="test-proj",
        base_path="/tmp",
    )


class TestEnrichThenPersistStrategy:
    def test_noop_when_ids_empty(self) -> None:
        indexer = MagicMock()
        strategy = EnrichThenPersistStrategy(finding_repo=MagicMock(), indexer=indexer)
        mock_pipeline = MagicMock()
        with patch(
            "application.pipeline.strategies.EnrichmentPipeline",
            return_value=mock_pipeline,
        ):
            strategy.handle(_event(ids=[]))

        mock_pipeline.enrich.assert_not_called()
        indexer.index_findings.assert_not_called()

    def test_calls_enrichment_pipeline_with_ids(self) -> None:
        mock_repo = MagicMock()
        indexer = MagicMock()
        strategy = EnrichThenPersistStrategy(finding_repo=mock_repo, indexer=indexer)
        mock_pipeline = MagicMock()
        mock_kb = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ) as mock_cls,
            patch.object(strategy, "_get_knowledge_base", return_value=mock_kb),
        ):
            strategy.handle(_event(ids=[1, 2]))

        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["finding_repo"] is mock_repo
        mock_pipeline.enrich.assert_called_once_with([1, 2])

    def test_indexes_after_enrichment(self) -> None:
        call_order: list[str] = []
        indexer = MagicMock()
        indexer.index_findings.side_effect = lambda *_a, **_kw: call_order.append(
            "index"
        )
        strategy = EnrichThenPersistStrategy(finding_repo=MagicMock(), indexer=indexer)
        mock_pipeline = MagicMock()
        mock_pipeline.enrich.side_effect = lambda _: call_order.append("enrich")
        mock_kb = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
            patch.object(strategy, "_get_knowledge_base", return_value=mock_kb),
        ):
            strategy.handle(_event(ids=[1]))

        assert call_order == ["enrich", "index"]

    def test_passes_kb_and_ids_to_indexer(self) -> None:
        indexer = MagicMock()
        strategy = EnrichThenPersistStrategy(finding_repo=MagicMock(), indexer=indexer)
        mock_pipeline = MagicMock()
        mock_kb = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
            patch.object(strategy, "_get_knowledge_base", return_value=mock_kb),
        ):
            strategy.handle(_event(ids=[5]))

        indexer.index_findings.assert_called_once_with(
            mock_kb, [5], caller_label="EnrichThenPersistStrategy"
        )

    def test_skips_indexer_when_kb_init_fails(self) -> None:
        indexer = MagicMock()
        strategy = EnrichThenPersistStrategy(finding_repo=MagicMock(), indexer=indexer)
        mock_pipeline = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
            patch.object(
                strategy,
                "_get_knowledge_base",
                side_effect=RuntimeError("kb boom"),
            ),
        ):
            strategy.handle(_event(ids=[1, 2]))

        indexer.index_findings.assert_not_called()
