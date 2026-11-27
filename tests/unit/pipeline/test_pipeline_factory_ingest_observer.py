"""Tests for the ingest observer hook on PipelineFactory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.factory import PipelineFactory
from domain.pipeline.events import IngestCompleted


class TestPipelineFactoryIngestObserver:
    def test_observer_runs_before_the_post_ingest_strategy(self) -> None:
        calls: list[str] = []
        with patch("application.pipeline.factory.PersistOnlyStrategy") as strategy_cls:
            strategy_cls.return_value.handle.side_effect = lambda e: calls.append(
                "strategy"
            )
            bus = PipelineFactory.create(
                finding_repo=MagicMock(),
                repo_repo=MagicMock(),
                url_finding_repo=MagicMock(),
                skip_enrichment=True,
                ingest_observer=lambda e: calls.append("observer"),
            )
        bus.dispatch(
            IngestCompleted(
                ids=[], failed_tools=[], run_id=1, project_name="p", base_path="/tmp"
            )
        )
        assert calls == ["observer", "strategy"]
