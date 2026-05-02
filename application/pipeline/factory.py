"""PipelineFactory: creates a wired EventBus for a scan run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.pipeline.handlers import IngestHandler
from application.pipeline.strategies import (
    EnrichThenPersistStrategy,
    PersistOnlyStrategy,
    PostIngestStrategy,
)
from application.url_inventory.ingest_handler import UrlInventoryIngestHandler
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted

if TYPE_CHECKING:
    from application.locking.cancellation import CancellationToken
    from application.ports.progress_reporter import ProgressReporter
    from application.ports.scan_event_sink import ScanEventSink


class PipelineFactory:
    """Creates a fully-wired EventBus for a single scan run.

    Separates pipeline construction from scan execution so the post-ingest
    strategy can vary without touching any scan type, orchestrator, or REPL
    code.
    """

    @staticmethod
    def create(
        reporter: ProgressReporter | None = None,
        skip_enrichment: bool = False,
        project_id: int | None = None,
        event_sink: ScanEventSink | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> EventBus:
        """Return an EventBus wired with the appropriate post-ingest strategy."""
        bus = EventBus()

        # Findings ingest pipeline
        ingest = IngestHandler(bus)
        bus.subscribe(ToolCompleted, ingest.handle)

        strategy: PostIngestStrategy
        if skip_enrichment:
            strategy = PersistOnlyStrategy()
        else:
            strategy = EnrichThenPersistStrategy(
                reporter=reporter,
                project_id=project_id,
                event_sink=event_sink,
                cancel_token=cancel_token,
            )

        bus.subscribe(IngestCompleted, strategy.handle)

        # URL discovery pipeline (Phase 9): single handler routes Katana / Noir
        # output through ``UrlInventoryService`` (writes ``url_findings`` rows
        # and rebuilds the merged seeds / OAS3 artifacts on disk for
        # downstream DAST tools).
        url_inventory = UrlInventoryIngestHandler()
        bus.subscribe(ToolCompleted, url_inventory.handle)

        return bus
