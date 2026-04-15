"""Unit tests for PipelineFactory."""

from __future__ import annotations

from application.pipeline.factory import PipelineFactory
from application.pipeline.handlers import IngestHandler
from application.pipeline.strategies import (
    EnrichThenPersistStrategy,
    PersistOnlyStrategy,
)
from application.pipeline.url_handlers import URLSourceEmitter
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted


class TestPipelineFactory:
    def test_returns_event_bus(self) -> None:
        bus = PipelineFactory.create()
        assert isinstance(bus, EventBus)

    def test_default_subscribes_enrich_then_persist(self) -> None:
        bus = PipelineFactory.create(skip_enrichment=False)
        handlers = bus._handlers[IngestCompleted]
        assert len(handlers) == 1
        assert isinstance(handlers[0].__self__, EnrichThenPersistStrategy)

    def test_skip_enrichment_subscribes_persist_only(self) -> None:
        bus = PipelineFactory.create(skip_enrichment=True)
        handlers = bus._handlers[IngestCompleted]
        assert len(handlers) == 1
        assert isinstance(handlers[0].__self__, PersistOnlyStrategy)

    def test_ingest_handler_always_subscribed(self) -> None:
        for skip in (True, False):
            bus = PipelineFactory.create(skip_enrichment=skip)
            handler_types = {type(h.__self__) for h in bus._handlers[ToolCompleted]}
            assert IngestHandler in handler_types
            assert URLSourceEmitter in handler_types

    def test_two_calls_return_independent_buses(self) -> None:
        bus_a = PipelineFactory.create()
        bus_b = PipelineFactory.create()
        assert bus_a is not bus_b
        assert bus_a._handlers is not bus_b._handlers
