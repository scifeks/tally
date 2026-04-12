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
        strategy = EnrichThenPersistStrategy()
        mock_pipeline = MagicMock()
        with patch(
            "application.pipeline.strategies.EnrichmentPipeline",
            return_value=mock_pipeline,
        ):
            strategy.handle(_event(ids=[]))

        mock_pipeline.enrich.assert_not_called()

    def test_calls_enrichment_pipeline_with_ids(self) -> None:
        strategy = EnrichThenPersistStrategy()
        mock_repo = MagicMock()
        mock_pipeline = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.make_store",
                return_value=(MagicMock(), mock_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ) as mock_cls,
            patch.object(strategy, "_persist_to_chromadb"),
        ):
            strategy.handle(_event(ids=[1, 2]))

        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["finding_repo"] is mock_repo
        mock_pipeline.enrich.assert_called_once_with([1, 2])

    def test_persists_to_chromadb_after_enrichment(self) -> None:
        call_order: list[str] = []
        strategy = EnrichThenPersistStrategy()
        mock_pipeline = MagicMock()
        mock_pipeline.enrich.side_effect = lambda _: call_order.append("enrich")

        with (
            patch(
                "application.pipeline.strategies.make_store",
                return_value=(MagicMock(), MagicMock(), MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
            patch.object(
                strategy,
                "_persist_to_chromadb",
                side_effect=lambda *_: call_order.append("chroma"),
            ),
        ):
            strategy.handle(_event(ids=[1]))

        assert call_order == ["enrich", "chroma"]

    def test_passes_base_path_and_project_to_persist(self) -> None:
        strategy = EnrichThenPersistStrategy()
        mock_pipeline = MagicMock()

        with (
            patch(
                "application.pipeline.strategies.make_store",
                return_value=(MagicMock(), MagicMock(), MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.strategies.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
            patch.object(strategy, "_persist_to_chromadb") as mock_persist,
        ):
            strategy.handle(_event(ids=[5]))

        mock_persist.assert_called_once_with([5], "test-proj", "/tmp")
