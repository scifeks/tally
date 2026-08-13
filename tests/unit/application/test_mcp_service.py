"""Unit tests for McpTriageService."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.mcp.service import McpTriageService
from domain.triage.entry import TriageBatchRow, TriageRunSummary


def _make_batch_row(
    batch_id: int = 1,
    run_id: int = 1,
    status: str = "in_progress",
) -> TriageBatchRow:
    return TriageBatchRow(
        id=batch_id,
        run_id=run_id,
        finding_ids=[101, 102],
        batch_data=[
            {"id": 101, "tool": "semgrep", "file": "main.py", "severity": "high"},
            {"id": 102, "tool": "semgrep", "file": "utils.py", "severity": "medium"},
        ],
        status=status,
        run_attempts=1,
        created_at="2024-01-01T00:00:00Z",
        started_at="2024-01-01T00:00:01Z",
        completed_at=None,
    )


def _make_service(
    triage_repo: MagicMock | None = None,
    finding_repo: MagicMock | None = None,
    run_repo: MagicMock | None = None,
    tool_registry: MagicMock | None = None,
) -> McpTriageService:
    return McpTriageService(
        triage_repo=triage_repo or MagicMock(),
        finding_repo=finding_repo or MagicMock(),
        run_repo=run_repo or MagicMock(),
        tool_registry=tool_registry or MagicMock(),
    )


class TestFetchBatch:
    def test_fetch_batch_claims_pending(self) -> None:
        """Pending batches exist, claim returns batch, renders prompts."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1

        triage_repo = MagicMock()
        batch = _make_batch_row(batch_id=5, run_id=1, status="in_progress")
        triage_repo.claim_batch.return_value = batch
        summary = TriageRunSummary(
            scan_run_id=1,
            status="in_progress",
            started_at="2024-01-01T00:00:00Z",
            finished_at=None,
            total_findings=10,
            processed_findings=2,
            total_batches=5,
            counts_by_status={"completed": 1, "in_progress": 1, "pending": 3},
        )
        triage_repo.summarize_for_run.return_value = summary

        tool = MagicMock()
        tool.scan_segment = "sast"
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool

        service = _make_service(
            triage_repo=triage_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
        )

        result = service.fetch_batch("test-project")

        assert result["batch_id"] == 5
        assert result["run_id"] == 1
        assert result["segment"] == "sast"
        assert result["total_batches"] == 5
        assert result["completed_batches"] == 1
        assert len(result["findings"]) == 2
        assert result["findings"][0]["finding_id"] == 101

    def test_fetch_batch_computes_new_batches(self) -> None:
        """No pending batches, untriaged findings exist, compute+create+claim."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1

        triage_repo = MagicMock()
        # First claim returns None (no pending batch)
        # Second claim (after compute) returns a batch
        batch = _make_batch_row(batch_id=10, run_id=1)
        triage_repo.claim_batch.side_effect = [None, batch]

        # Simulate untriaged findings
        triage_repo.get_active_finding_combos.return_value = [
            ("semgrep", "repo1", "sast")
        ]
        findings = [
            {"id": 201, "tool": "semgrep", "file": "app.py", "severity": "high"},
            {"id": 202, "tool": "semgrep", "file": "app.py", "severity": "low"},
        ]
        triage_repo.fetch_active_findings_for_batching.return_value = findings
        triage_repo.create_batches.return_value = [(1, 1), (2, 1)]

        summary = TriageRunSummary(
            scan_run_id=1,
            status="in_progress",
            started_at="2024-01-01T00:00:00Z",
            finished_at=None,
            total_findings=2,
            processed_findings=0,
            total_batches=2,
            counts_by_status={"pending": 2},
        )
        triage_repo.summarize_for_run.return_value = summary

        tool = MagicMock()
        tool.scan_segment = "sast"
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool

        service = _make_service(
            triage_repo=triage_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
        )

        result = service.fetch_batch("test-project")

        assert result["batch_id"] == 10
        assert result["total_batches"] == 2
        triage_repo.create_batches.assert_called_once()

    def test_fetch_batch_no_findings(self) -> None:
        """No untriaged findings, returns null batch_id."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1

        triage_repo = MagicMock()
        triage_repo.claim_batch.return_value = None
        triage_repo.get_active_finding_combos.return_value = []

        service = _make_service(
            triage_repo=triage_repo,
            run_repo=run_repo,
        )

        result = service.fetch_batch("test-project")

        assert result["batch_id"] is None
        assert "message" in result
        assert "No untriaged findings" in result["message"]

    def test_fetch_batch_no_scan_runs(self) -> None:
        """latest_run_id returns None, returns message."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = None

        service = _make_service(run_repo=run_repo)

        result = service.fetch_batch("test-project")

        assert result["batch_id"] is None
        assert "No scan runs" in result["message"]


class TestSubmitVerdicts:
    def test_submit_verdicts_all_accepted(self) -> None:
        """All verdicts valid, all findings updated, batch completed."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1

        finding_repo = MagicMock()
        finding_repo.update_finding.return_value = True

        triage_repo = MagicMock()
        batch = _make_batch_row(batch_id=1, run_id=1)
        triage_repo.list_for_run.return_value = [batch]

        tool = MagicMock()
        tool.scan_segment = "sast"
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool

        service = _make_service(
            triage_repo=triage_repo,
            finding_repo=finding_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
        )

        verdicts = [
            {
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
            },
            {
                "finding_id": 102,
                "confidence": "probable",
                "finding_type": "vulnerability",
                "severity": "medium",
                "reasoning": "Possible issue",
                "remediation": "Review code",
                "attack_vector": "local",
                "access_required": "authenticated",
                "exploitation_complexity": "high",
                "user_interaction": "required",
            },
        ]

        result = service.submit_verdicts(1, verdicts, project_name="test-project")

        assert result["batch_status"] == "completed"
        assert len(result["results"]) == 2
        assert all(r["status"] == "accepted" for r in result["results"])
        assert finding_repo.update_finding.call_count == 2
        triage_repo.complete_batch.assert_called_once_with(1, "completed")

    def test_submit_verdicts_partial(self) -> None:
        """Some valid some invalid, valid ones persisted, errors returned."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1

        finding_repo = MagicMock()
        finding_repo.update_finding.return_value = True

        triage_repo = MagicMock()
        batch = _make_batch_row(batch_id=1, run_id=1)
        triage_repo.list_for_run.return_value = [batch]

        tool = MagicMock()
        tool.scan_segment = "sast"
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool

        service = _make_service(
            triage_repo=triage_repo,
            finding_repo=finding_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
        )

        verdicts = [
            {
                "finding_id": 101,
                "confidence": "confirmed",
                "finding_type": "vulnerability",
                "severity": "high",
                "reasoning": "Clear XSS",
                "remediation": "Escape",
                "attack_vector": "network",
                "access_required": "none",
                "exploitation_complexity": "low",
                "user_interaction": "required",
            },
            {
                "finding_id": 102,
                # Missing required field
            },
        ]

        result = service.submit_verdicts(1, verdicts, project_name="test-project")

        assert len(result["results"]) == 2
        assert result["results"][0]["status"] == "accepted"
        assert result["results"][1]["status"] == "rejected"
        assert "error" in result["results"][1]
        assert result["batch_status"] == "completed"
        triage_repo.complete_batch.assert_called_once_with(1, "completed")

    def test_submit_verdicts_all_rejected(self) -> None:
        """All invalid, batch completed as failed."""
        run_repo = MagicMock()
        run_repo.latest_run_id.return_value = 1

        triage_repo = MagicMock()
        batch = _make_batch_row(batch_id=1, run_id=1)
        triage_repo.list_for_run.return_value = [batch]

        tool = MagicMock()
        tool.scan_segment = "sast"
        tool_registry = MagicMock()
        tool_registry.get_tool.return_value = tool

        service = _make_service(
            triage_repo=triage_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
        )

        verdicts = [
            {"finding_id": 101},  # Missing all required fields
            {"finding_id": 102},  # Missing all required fields
        ]

        result = service.submit_verdicts(1, verdicts, project_name="test-project")

        assert result["batch_status"] == "failed"
        assert all(r["status"] == "rejected" for r in result["results"])
        triage_repo.complete_batch.assert_called_once_with(1, "failed")


class TestSkipBatch:
    def test_skip_batch(self) -> None:
        """Transitions to skipped."""
        triage_repo = MagicMock()
        service = _make_service(triage_repo=triage_repo)

        result = service.skip_batch(5)

        assert result["status"] == "skipped"
        triage_repo.complete_batch.assert_called_once_with(5, "skipped")
