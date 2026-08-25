"""Verify the scan worker persists run_tools after a successful scan."""

from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from application.ports.tool_runner import CliToolRunnerPort
from application.tools.scan_service import ScanService
from domain.tools.scan_types import ScanSummary


@pytest.fixture
def run_repo() -> MagicMock:
    repo = MagicMock()
    repo.create.return_value = 42
    repo.get.return_value = None
    return repo


def _make_summary(findings_by_tool: dict[str, int]) -> ScanSummary:
    return ScanSummary(
        total_tools_run=len(findings_by_tool),
        total_tools_skipped=0,
        total_tools_failed=0,
        results=[],
        duration_seconds=1.0,
        findings_ingested=sum(findings_by_tool.values()),
        findings_by_tool=findings_by_tool,
    )


def _call_worker(
    run_repo: MagicMock,
    summary: ScanSummary,
) -> Future[ScanSummary]:
    future: Future[ScanSummary] = Future()
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_scoped_scan.return_value = summary

    with (
        patch("application.pipeline.factory.PipelineFactory") as mock_pf,
        patch("application.tools.scan_service.ScanOrchestrator") as mock_orch_cls,
        patch("application.tools.scan_service.ToolExecutor"),
        patch("application.sync.integration_sync.run_configured_syncs"),
    ):
        mock_pf.create.return_value = MagicMock()
        mock_orch_cls.return_value = mock_orchestrator

        svc = ScanService(
            cli_tool_runner=MagicMock(
                spec=CliToolRunnerPort,
            ),
        )
        svc._run_worker(
            future=future,
            holder_token="test",
            run_id=42,
            project_id=1,
            project_name="proj",
            base_path="/tmp",
            tool_registry=MagicMock(),
            repo_ids=(),
            tool_ids=(),
            domains=(),
            skip_tool_ids=(),
            skip_enrichment=False,
            prompt=MagicMock(),
            reporter=None,
            event_sink=None,
            display=None,
            cancel_token=MagicMock(is_set=MagicMock(return_value=False)),
            run_repo=run_repo,
            chat_session_repo=MagicMock(),
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            url_finding_repo=MagicMock(),
        )
    return future


class TestWorkerPersistsRunTools:
    def test_worker_calls_add_run_tools(self, run_repo: MagicMock) -> None:
        summary = _make_summary({"semgrep": 5, "dalfox": 10})
        _call_worker(run_repo, summary)

        run_repo.add_run_tools.assert_called_once()
        call_args = run_repo.add_run_tools.call_args
        assert call_args[0][0] == 42
        tools = {r["tool"]: r["findings_count"] for r in call_args[0][1]}
        assert tools == {"semgrep": 5, "dalfox": 10}

    def test_worker_skips_when_no_tools_ran(self, run_repo: MagicMock) -> None:
        summary = _make_summary({})
        _call_worker(run_repo, summary)
        run_repo.add_run_tools.assert_not_called()
