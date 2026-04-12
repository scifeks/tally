"""PipelineFactory: creates a wired EventBus for a scan run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.pipeline.handlers import IngestHandler
from application.pipeline.strategies import (
    EnrichThenPersistStrategy,
    PersistOnlyStrategy,
    PostIngestStrategy,
)
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted

if TYPE_CHECKING:
    from rich.console import Console


class PipelineFactory:
    """Creates a fully-wired EventBus for a single scan run.

    Separates pipeline construction from scan execution so the post-ingest
    strategy can vary without touching any scan type, orchestrator, or REPL
    code.
    """

    @staticmethod
    def create(
        console: Console | None = None,
        skip_enrichment: bool = False,
    ) -> EventBus:
        """Return an EventBus wired with the appropriate post-ingest strategy.

        Args:
            console:          Rich console forwarded to handlers for progress output.
            skip_enrichment:  When ``True``, findings are written to ChromaDB
                              immediately after ingest — no LLM enrichment calls
                              are made.  When ``False`` (default), the full
                              enrich-then-persist path is used.
        """
        bus = EventBus()
        ingest = IngestHandler(bus, console=console)
        bus.subscribe(ToolCompleted, ingest.handle)

        strategy: PostIngestStrategy
        if skip_enrichment:
            strategy = PersistOnlyStrategy(console=console)
        else:
            strategy = EnrichThenPersistStrategy(console=console)

        bus.subscribe(IngestCompleted, strategy.handle)
        return bus
