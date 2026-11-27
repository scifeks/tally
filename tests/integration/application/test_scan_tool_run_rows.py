"""Tests that a scan's events end up as real run_tools rows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.ports.scan_event_sink import FanOutScanEventSink
from application.scans.tool_run_recorder import ToolRunRecorder
from domain.pipeline import scan_events as se
from domain.pipeline.events import EventBus, IngestCompleted
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import (
    RepositoryRepository,
)
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


def _ingest(tool: str, service: str, stored: bool, ids: list[int]) -> IngestCompleted:
    return IngestCompleted(
        ids=ids,
        failed_tools=[],
        run_id=1,
        project_name="p",
        base_path="/tmp",
        tool=tool,
        repo="shop",
        service=service,
        stored=stored,
    )


class TestScanToolRunRows:
    def test_each_service_gets_its_own_row_and_only_stored_runs_are_done(
        self, tmp_path: Path
    ) -> None:
        factory = ConnectionFactory(tmp_path / "tally.db")
        factory.init_schema()
        with factory.connect() as conn:
            conn.execute("INSERT INTO repositories (name) VALUES ('shop')")
        runs = RunRepository(factory)
        run_id = runs.create(
            project_id=1, repo_ids=[], tool_ids=[], domains=[], skip_enrichment=True
        )
        recorder = ToolRunRecorder(
            runs,
            RepositoryRepository(factory),
            run_id=run_id,
            domain_of=lambda tool: "code",
        )
        adapter_sink = MagicMock()
        sink = FanOutScanEventSink([recorder, adapter_sink])
        bus = EventBus()
        bus.subscribe(IngestCompleted, recorder.on_ingest_completed)

        def tool(service: str, name: str) -> dict:
            return {
                "run_id": run_id,
                "project_id": 1,
                "repo": "shop",
                "service": service,
                "tool": name,
            }

        sink.emit(se.ToolStarted(**tool("api", "semgrep")))
        sink.emit(se.ToolCompleted(**tool("api", "semgrep"), exit_code=0))
        bus.dispatch(_ingest("semgrep", "api", True, [1, 2, 3]))

        sink.emit(se.ToolStarted(**tool("ui", "semgrep")))
        sink.emit(se.ToolCompleted(**tool("ui", "semgrep"), exit_code=0))
        bus.dispatch(_ingest("semgrep", "ui", False, []))

        sink.emit(
            se.ToolSkipped(
                **tool("ui", "composer-audit"),
                skip_reason="no manifest found for ui",
                kind=se.SKIP_NOT_APPLICABLE,
            )
        )
        sink.emit(se.ToolStarted(**tool("api", "gitleaks")))
        sink.emit(se.RunCancelled(run_id=run_id, project_id=1))

        bundle = runs.get_with_tool_runs(run_id)
        assert bundle is not None
        rows = {(r.tool, r.service): (r.status, r.findings_count) for r in bundle[1]}
        assert rows == {
            ("semgrep", "api"): ("done", 3),
            ("semgrep", "ui"): ("failed", 0),
            ("gitleaks", "api"): ("failed", 0),
        }
        assert adapter_sink.emit.call_count == 7
