"""Unit tests for PersistenceHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.handlers import PersistenceHandler
from domain.pipeline.events import EnrichmentCompleted, EventBus


def _enrich_completed(
    ids: list[int] | None = None,
    partial_success: bool = True,
    run_id: int | None = 1,
) -> EnrichmentCompleted:
    return EnrichmentCompleted(
        ids=ids if ids is not None else [1],
        partial_success=partial_success,
        run_id=run_id,
        project_name="test-proj",
        base_path="/tmp",
    )


class TestPersistenceHandler:
    def test_noop_when_run_id_is_none(self) -> None:
        bus = EventBus()
        mock_engine = MagicMock()
        mock_finding_repo = MagicMock()

        handler = PersistenceHandler(bus)
        with (
            patch(
                "application.pipeline.handlers.PersistenceHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
        ):
            handler.handle(_enrich_completed(run_id=None))

        mock_finding_repo.upsert_findings.assert_not_called()

    def test_calls_upsert_findings_with_fetched_metadata(self) -> None:
        bus = EventBus()

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.side_effect = lambda doc_id: {
            "id": doc_id,
            "document": "text",
            "metadata": {"tool": "semgrep", "doc_id": doc_id},
        }
        mock_finding_repo = MagicMock()

        handler = PersistenceHandler(bus)
        with (
            patch(
                "application.pipeline.handlers.PersistenceHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
        ):
            handler.handle(_enrich_completed(ids=[1, 2], run_id=42))

        mock_finding_repo.upsert_findings.assert_called_once_with(
            42,
            [
                {"tool": "semgrep", "doc_id": "1"},
                {"tool": "semgrep", "doc_id": "2"},
            ],
        )
