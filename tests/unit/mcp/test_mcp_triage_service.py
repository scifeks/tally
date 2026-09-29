"""Unit tests for McpTriageService's batch-fetch and status-summary logic."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.mcp.service import McpTriageService
from domain.pipeline.triage_events import BatchCompleted, BatchFailed, BatchStarted


class TestFetchBatchNoBatchCreation:
    def _make_service(
        self, *, claim_result: MagicMock | None = None
    ) -> tuple[McpTriageService, MagicMock]:
        triage_repo = MagicMock()
        triage_repo.claim_batch.return_value = claim_result
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1
        service = McpTriageService(
            triage_repo=triage_repo,
            finding_repo=MagicMock(),
            run_repo=run_repo,
            tool_registry=MagicMock(),
        )
        return service, triage_repo

    def test_returns_null_when_no_batches(self) -> None:
        svc, _ = self._make_service(claim_result=None)
        result = svc.fetch_batch("myproject")
        assert result["batch_id"] is None

    def test_does_not_call_compute(self) -> None:
        svc, triage_repo = self._make_service(claim_result=None)
        svc.fetch_batch("myproject")
        assert not hasattr(svc, "_compute_batches_for_run")
        assert not triage_repo.create_batches.called


class TestFetchBatchClaimsBatch:
    """Behavior once the repo hands back a claimed batch."""

    def _make_service(
        self,
        *,
        event_sink: MagicMock | None = None,
        segment: str = "sast",
    ) -> tuple[McpTriageService, MagicMock]:
        triage_repo = MagicMock()
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 7

        batch = MagicMock()
        batch.id = 42
        batch.batch_data = [{"id": 101, "tool": "semgrep", "repo": "acme/webapp"}]
        triage_repo.claim_batch.return_value = batch

        summary = MagicMock()
        summary.total_batches = 3
        summary.counts_by_status = {"completed": 1, "skipped": 0, "failed": 0}
        triage_repo.summarize_for_run.return_value = summary

        tool_obj = MagicMock()
        tool_obj.scan_segment = segment
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool_obj

        service = McpTriageService(
            triage_repo=triage_repo,
            finding_repo=MagicMock(),
            run_repo=run_repo,
            tool_registry=tool_registry,
            event_sink=event_sink,
        )
        return service, batch

    def test_includes_repo_name_from_batch_data(self) -> None:
        service, _ = self._make_service()
        result = service.fetch_batch("acme")
        assert result["repo_name"] == "acme/webapp"

    def test_repo_name_is_none_when_batch_has_no_findings(self) -> None:
        service, batch = self._make_service()
        batch.batch_data = []
        result = service.fetch_batch("acme")
        assert result["repo_name"] is None

    def test_emits_batch_started_with_claimed_batch_fields(self) -> None:
        event_sink = MagicMock()
        service, _ = self._make_service(event_sink=event_sink)

        service.fetch_batch("acme")

        event_sink.emit.assert_called_once()
        event = event_sink.emit.call_args.args[0]
        assert isinstance(event, BatchStarted)
        assert event.scan_run_id == 7
        assert event.batch_id == 42
        assert event.segment == "sast"

    def test_no_emission_without_event_sink(self) -> None:
        service, _ = self._make_service(event_sink=None)
        result = service.fetch_batch("acme")
        assert result["batch_id"] == 42


class TestSubmitVerdictsEmitsEvents:
    """Batch completion/failure events fired once verdicts are persisted."""

    _ACCEPTED_VERDICT = {
        "finding_id": 101,
        "confidence": "confirmed",
        "finding_type": "vulnerability",
        "severity": "high",
        "reasoning": "Clear XSS vector",
        "remediation": "Escape user input",
        "attack_vector": "network",
        "access_required": "none",
        "exploitation_complexity": "low",
        "user_interaction": "required",
    }

    def _make_service(
        self, *, event_sink: MagicMock | None = None
    ) -> tuple[McpTriageService, MagicMock]:
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 9

        batch = MagicMock()
        batch.id = 1
        batch.run_id = 9
        batch.batch_data = [
            {"id": 101, "tool": "semgrep"},
            {"id": 102, "tool": "semgrep"},
        ]

        triage_repo = MagicMock()
        triage_repo.list_for_run.return_value = [batch]

        finding_repo = MagicMock()
        finding_repo.update_finding.return_value = True

        tool_obj = MagicMock()
        tool_obj.scan_segment = "sast"
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool_obj

        service = McpTriageService(
            triage_repo=triage_repo,
            finding_repo=finding_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
            event_sink=event_sink,
        )
        return service, triage_repo

    def test_emits_batch_completed_when_verdicts_accepted(self) -> None:
        event_sink = MagicMock()
        service, _ = self._make_service(event_sink=event_sink)

        service.submit_verdicts(1, [self._ACCEPTED_VERDICT], project_name="acme")

        event_sink.emit.assert_called_once()
        event = event_sink.emit.call_args.args[0]
        assert isinstance(event, BatchCompleted)
        assert event.scan_run_id == 9
        assert event.batch_id == 1
        assert event.segment == "sast"
        assert event.findings_count == 1

    def test_emits_batch_failed_when_all_verdicts_rejected(self) -> None:
        event_sink = MagicMock()
        service, _ = self._make_service(event_sink=event_sink)

        service.submit_verdicts(1, [{"finding_id": 101}], project_name="acme")

        event_sink.emit.assert_called_once()
        event = event_sink.emit.call_args.args[0]
        assert isinstance(event, BatchFailed)
        assert event.scan_run_id == 9
        assert event.batch_id == 1

    def test_no_emission_without_event_sink(self) -> None:
        service, triage_repo = self._make_service(event_sink=None)

        result = service.submit_verdicts(
            1, [self._ACCEPTED_VERDICT], project_name="acme"
        )

        assert result["batch_status"] == "completed"
        triage_repo.complete_batch.assert_called_once_with(1, "completed")


class TestGetTriageStatus:
    """Status summary without claiming a batch."""

    def _make_service(
        self,
        *,
        latest_run_id: int | None,
        summary: MagicMock | None,
        max_concurrent_agents: int = 3,
    ) -> tuple[McpTriageService, MagicMock]:
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = latest_run_id
        triage_repo = MagicMock()
        triage_repo.summarize_for_run.return_value = summary
        service = McpTriageService(
            triage_repo=triage_repo,
            finding_repo=MagicMock(),
            run_repo=run_repo,
            tool_registry=MagicMock(),
            max_concurrent_agents=max_concurrent_agents,
        )
        return service, triage_repo

    def test_zeroed_summary_when_no_scan_runs(self) -> None:
        service, triage_repo = self._make_service(
            latest_run_id=None, summary=None, max_concurrent_agents=5
        )

        result = service.get_triage_status("acme")

        assert result == {
            "pending_batches": 0,
            "completed_batches": 0,
            "failed_batches": 0,
            "total_findings": 0,
            "max_concurrent_agents": 5,
        }
        triage_repo.summarize_for_run.assert_not_called()

    def test_zeroed_summary_when_run_has_no_batches_yet(self) -> None:
        service, triage_repo = self._make_service(latest_run_id=3, summary=None)

        result = service.get_triage_status("acme")

        assert result["pending_batches"] == 0
        triage_repo.summarize_for_run.assert_called_once_with(3)

    def test_aggregates_counts_from_summary(self) -> None:
        summary = MagicMock()
        summary.counts_by_status = {
            "pending": 4,
            "completed": 2,
            "skipped": 1,
            "failed": 1,
        }
        summary.total_findings = 20
        service, _ = self._make_service(
            latest_run_id=3, summary=summary, max_concurrent_agents=2
        )

        result = service.get_triage_status("acme")

        assert result == {
            "pending_batches": 4,
            "completed_batches": 3,
            "failed_batches": 1,
            "total_findings": 20,
            "max_concurrent_agents": 2,
        }
