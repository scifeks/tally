"""Unit tests for ChromaDBHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.handlers import ChromaDBHandler
from domain.pipeline.events import EnrichmentCompleted


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


class TestChromaDBHandler:
    def test_noop_when_ids_empty(self) -> None:
        mock_engine = MagicMock()
        handler = ChromaDBHandler()
        with patch(
            "application.pipeline.handlers.ChromaDBHandler._get_engine",
            return_value=mock_engine,
        ):
            handler.handle(_enrich_completed(ids=[]))

        mock_engine.add_documents.assert_not_called()
        mock_engine.delete_findings.assert_not_called()

    def test_engine_init_failure_returns_early(self) -> None:
        mock_finding_repo = MagicMock()
        handler = ChromaDBHandler()
        with (
            patch(
                "application.pipeline.handlers.ChromaDBHandler._get_engine",
                side_effect=RuntimeError("init failed"),
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
        ):
            handler.handle(_enrich_completed(ids=[1]))

        mock_finding_repo.get_by_ids.assert_not_called()

    def test_calls_delete_and_add_documents_per_group(self) -> None:
        mock_engine = MagicMock()
        mock_finding_repo = MagicMock()
        mock_finding_repo.get_by_ids.return_value = [
            {"id": 1, "tool": "nmap", "profile": "default", "host": "10.0.0.1"},
            {"id": 2, "tool": "nmap", "profile": "default", "host": "10.0.0.2"},
        ]
        mock_tool_handler = MagicMock()
        mock_tool_handler.render.side_effect = lambda row: f"nmap row {row['id']}"

        handler = ChromaDBHandler()
        with (
            patch(
                "application.pipeline.handlers.ChromaDBHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.ToolHandlerFactory.load",
                return_value=mock_tool_handler,
            ),
        ):
            handler.handle(_enrich_completed(ids=[1, 2]))

        mock_engine.delete_findings.assert_called_once_with("nmap", "default")
        mock_engine.add_documents.assert_called_once_with(
            texts=["nmap row 1", "nmap row 2"],
            metadatas=[
                {"tool": "nmap", "profile": "default"},
                {"tool": "nmap", "profile": "default"},
            ],
            ids=["1", "2"],
        )

    def test_groups_by_tool_and_profile(self) -> None:
        mock_engine = MagicMock()
        mock_finding_repo = MagicMock()
        mock_finding_repo.get_by_ids.return_value = [
            {"id": 1, "tool": "nmap", "profile": "default"},
            {"id": 2, "tool": "gitleaks", "profile": "default"},
        ]
        mock_nmap_handler = MagicMock()
        mock_nmap_handler.render.return_value = "nmap text"
        mock_gitleaks_handler = MagicMock()
        mock_gitleaks_handler.render.return_value = "gitleaks text"

        handler = ChromaDBHandler()
        with (
            patch(
                "application.pipeline.handlers.ChromaDBHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.ToolHandlerFactory.load",
                side_effect=lambda t: (
                    mock_nmap_handler if t == "nmap" else mock_gitleaks_handler
                ),
            ),
        ):
            handler.handle(_enrich_completed(ids=[1, 2]))

        assert mock_engine.delete_findings.call_count == 2
        assert mock_engine.add_documents.call_count == 2

    def test_skips_group_when_tool_handler_none(self) -> None:
        mock_engine = MagicMock()
        mock_finding_repo = MagicMock()
        mock_finding_repo.get_by_ids.return_value = [
            {"id": 1, "tool": "unknown-tool", "profile": "default"},
        ]

        handler = ChromaDBHandler()
        with (
            patch(
                "application.pipeline.handlers.ChromaDBHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.ToolHandlerFactory.load",
                return_value=None,
            ),
        ):
            handler.handle(_enrich_completed(ids=[1]))

        mock_engine.delete_findings.assert_called_once_with("unknown-tool", "default")
        mock_engine.add_documents.assert_not_called()
