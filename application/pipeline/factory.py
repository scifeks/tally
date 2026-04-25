"""PipelineFactory: creates a wired EventBus for a scan run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.pipeline.handlers import IngestHandler
from application.pipeline.strategies import (
    EnrichThenPersistStrategy,
    PersistOnlyStrategy,
    PostIngestStrategy,
)
from application.pipeline.url_handlers import (
    ConfigUpdateHandler,
    URLDedupeHandler,
    URLOS3Handler,
    URLSeedsHandler,
    URLSourceEmitter,
)
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted
from domain.pipeline.url_events import URLsConverted, URLsDeduped, URLSourceChanged

if TYPE_CHECKING:
    from rich.console import Console

    from application.ports.scan_event_sink import ScanEventSink


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
        project_id: int | None = None,
        event_sink: ScanEventSink | None = None,
    ) -> EventBus:
        """Return an EventBus wired with the appropriate post-ingest strategy.

        Args:
            console:          Rich console forwarded to handlers for progress output.
            skip_enrichment:  When ``True``, findings are written to ChromaDB
                              immediately after ingest — no LLM enrichment calls
                              are made.  When ``False`` (default), the full
                              enrich-then-persist path is used.
            project_id:       Numeric project id stamped on enrichment events.
            event_sink:       ``ScanEventSink`` for ``EnrichmentProgress`` /
                              ``EnrichmentComplete`` emission. Defaults to no-op.
        """
        bus = EventBus()

        # --- Findings ingest pipeline ---
        ingest = IngestHandler(bus, console=console)
        bus.subscribe(ToolCompleted, ingest.handle)

        strategy: PostIngestStrategy
        if skip_enrichment:
            strategy = PersistOnlyStrategy(console=console)
        else:
            strategy = EnrichThenPersistStrategy(
                console=console,
                project_id=project_id,
                event_sink=event_sink,
            )

        bus.subscribe(IngestCompleted, strategy.handle)

        # --- URL discovery pipeline ---
        # URLSourceEmitter and IngestHandler both subscribe to ToolCompleted;
        # they run sequentially (SQLite ingest then URL merge) per the bus
        # registration order.  Neither depends on the other's output.
        url_emitter = URLSourceEmitter(bus)
        url_deduper = URLDedupeHandler(bus)
        url_seeds = URLSeedsHandler()
        url_oas3 = URLOS3Handler()
        config_update = ConfigUpdateHandler()

        bus.subscribe(ToolCompleted, url_emitter.handle)
        bus.subscribe(URLSourceChanged, url_deduper.handle)
        bus.subscribe(URLsDeduped, url_seeds.handle)
        bus.subscribe(URLsDeduped, url_oas3.handle)
        bus.subscribe(URLsConverted, config_update.handle)

        return bus
