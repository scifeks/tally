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
        strategy = PersistOnlyStrategy()
        with patch.object(strategy, "_persist_to_chromadb") as mock_persist:
            strategy.handle(_event(ids=[]))
        mock_persist.assert_not_called()

    def test_never_calls_enrichment_pipeline(self) -> None:
        strategy = PersistOnlyStrategy()
        with (
            patch(
                "application.pipeline.strategies.EnrichmentPipeline"
            ) as mock_enrich_cls,
            patch.object(strategy, "_persist_to_chromadb"),
        ):
            strategy.handle(_event(ids=[1, 2]))
        mock_enrich_cls.assert_not_called()

    def test_calls_persist_to_chromadb_with_correct_args(self) -> None:
        strategy = PersistOnlyStrategy()
        with patch.object(strategy, "_persist_to_chromadb") as mock_persist:
            strategy.handle(_event(ids=[3, 4]))
        mock_persist.assert_called_once_with([3, 4], "test-proj", "/tmp")

    def test_chromadb_write_uses_engine_and_tool_handler(self) -> None:
        """Full _persist_to_chromadb path: groups by tool/profile."""
        strategy = PersistOnlyStrategy()
        mock_engine = MagicMock()
        mock_finding_repo = MagicMock()
        mock_finding_repo.get_by_ids.return_value = [
            {"id": 1, "tool": "gitleaks", "profile": "main"},
            {"id": 2, "tool": "gitleaks", "profile": "main"},
        ]
        mock_tool_handler = MagicMock()
        mock_tool_handler.render.side_effect = lambda row: f"secret {row['id']}"

        with (
            patch.object(strategy, "_get_engine", return_value=mock_engine),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.ToolHandlerFactory.load",
                return_value=mock_tool_handler,
            ),
        ):
            strategy.handle(_event(ids=[1, 2]))

        mock_engine.delete_findings.assert_called_once_with("gitleaks", "main")
        mock_engine.add_documents.assert_called_once_with(
            texts=["Repository: main | secret 1", "Repository: main | secret 2"],
            metadatas=[
                {"tool": "gitleaks", "profile": "main"},
                {"tool": "gitleaks", "profile": "main"},
            ],
            ids=["1", "2"],
        )
