"""Unit tests for PipelineFactory."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.pipeline.factory import PipelineFactory
from domain.pipeline.events import EventBus


class TestPipelineFactory:
    def test_returns_event_bus(self) -> None:
        bus = PipelineFactory.create(
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            url_finding_repo=MagicMock(),
        )
        assert isinstance(bus, EventBus)

    def test_creates_bus_with_enrich_disabled(self) -> None:
        bus = PipelineFactory.create(
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            url_finding_repo=MagicMock(),
            skip_enrichment=False,
        )
        assert isinstance(bus, EventBus)

    def test_creates_bus_with_enrich_enabled(self) -> None:
        bus = PipelineFactory.create(
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            url_finding_repo=MagicMock(),
            skip_enrichment=True,
        )
        assert isinstance(bus, EventBus)

    def test_two_calls_return_independent_buses(self) -> None:
        bus_a = PipelineFactory.create(
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            url_finding_repo=MagicMock(),
        )
        bus_b = PipelineFactory.create(
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            url_finding_repo=MagicMock(),
        )
        assert bus_a is not bus_b
