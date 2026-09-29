"""MCP triage service: core business logic for triage via MCP tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from application.triage.prompts import api_trace, dast_trace, sast_trace
from domain.findings.normalization import (
    build_triage_meta,
    normalise_finding_type,
    severity_to_rank,
)
from domain.triage.verdict import (
    VerdictParseError,
    parse_verdict,
)

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_batch_repository import TriageBatchRepositoryPort
    from application.ports.triage_event_sink import TriageEventSink
    from application.tools.registry import ToolRegistry


_PROMPT_RENDERERS: dict[str, Callable[..., str]] = {
    "api": api_trace.render,
    "sast": sast_trace.render,
    "web": dast_trace.render,
}

_log = logging.getLogger(__name__)


class McpTriageService:
    """Orchestrate batch fetch, prompt rendering, and verdict writing for MCP."""

    def __init__(
        self,
        *,
        triage_repo: TriageBatchRepositoryPort,
        finding_repo: FindingRepositoryPort,
        run_repo: RunRepositoryPort,
        tool_registry: ToolRegistry,
        event_sink: TriageEventSink | None = None,
        max_concurrent_agents: int = 3,
    ) -> None:
        self._triage_repo = triage_repo
        self._finding_repo = finding_repo
        self._run_repo = run_repo
        self._tool_registry = tool_registry
        self._event_sink = event_sink
        self._max_concurrent_agents = max_concurrent_agents

    def fetch_batch(self, project_name: str) -> dict[str, Any]:
        """Fetch the next pending triage batch."""
        latest_run_id = self._run_repo.latest_run_id()
        if latest_run_id is None:
            return {
                "batch_id": None,
                "message": f"No scan runs for project '{project_name}'",
            }

        run_id = latest_run_id
        batch = self._triage_repo.claim_batch(run_id)

        if batch is None:
            return {
                "batch_id": None,
                "message": f"No pending batches for '{project_name}'",
            }

        tool_name = batch.batch_data[0]["tool"] if batch.batch_data else None
        tool_obj = self._tool_registry.get_tool(tool_name or "") if tool_name else None
        segment = tool_obj.scan_segment if tool_obj else "sast"

        if self._event_sink:
            from domain.pipeline.triage_events import BatchStarted

            self._event_sink.emit(
                BatchStarted(
                    scan_run_id=run_id,
                    project_id=None,
                    batch_id=batch.id,
                    segment=segment,
                    message=f"MCP batch {batch.id} claimed",
                )
            )

        render_fn = _PROMPT_RENDERERS.get(segment)
        if render_fn is None:
            render_fn = sast_trace.render
        findings_with_prompts = []
        for finding in batch.batch_data:
            prompt = render_fn(finding, project=project_name)
            findings_with_prompts.append(
                {
                    "finding_id": finding.get("id"),
                    "prompt": prompt,
                }
            )

        # repo comes from the finding rows collected into this batch
        repo_name = batch.batch_data[0].get("repo") if batch.batch_data else None

        summary = self._triage_repo.summarize_for_run(run_id)
        total_batches = summary.total_batches if summary else 0
        completed_batches = (
            summary.counts_by_status.get("completed", 0)
            + summary.counts_by_status.get("skipped", 0)
            + summary.counts_by_status.get("failed", 0)
            if summary
            else 0
        )

        return {
            "batch_id": batch.id,
            "run_id": run_id,
            "segment": segment,
            "repo_name": repo_name,
            "total_batches": total_batches,
            "completed_batches": completed_batches,
            "findings": findings_with_prompts,
        }

    def submit_verdicts(
        self,
        batch_id: int,
        verdicts: list[dict[str, Any]],
        *,
        project_name: str,
    ) -> dict[str, Any]:
        """Process and persist a list of verdict dicts for a batch."""
        results = []
        accepted_count = 0
        rejected_count = 0

        run_id = self._get_run_id_for_batch(batch_id)
        all_batches = self._triage_repo.list_for_run(run_id)
        batch_row = next((b for b in all_batches if b.id == batch_id), None)
        segment = "sast"
        batch_finding_ids: set[Any] = set()
        if batch_row and batch_row.batch_data:
            tool_name = batch_row.batch_data[0].get("tool")
            tool_obj = (
                self._tool_registry.get_tool(tool_name or "") if tool_name else None
            )
            if tool_obj:
                segment = tool_obj.scan_segment
            batch_finding_ids = {
                f.get("id") for f in batch_row.batch_data if f.get("id") is not None
            }

        for verdict_dict in verdicts:
            finding_id = verdict_dict.get("finding_id")
            try:
                if not isinstance(finding_id, int):
                    raise VerdictParseError("finding_id must be an integer")
                if batch_finding_ids and finding_id not in batch_finding_ids:
                    raise VerdictParseError(
                        f"finding_id {finding_id} is not in batch {batch_id}"
                    )
                json_text = json.dumps(verdict_dict)
                verdict = parse_verdict(json_text, expected_finding_id=finding_id)

                call_stack_str = (
                    json.dumps(verdict.call_stack) if verdict.call_stack else None
                )
                self._finding_repo.update_finding(
                    verdict.finding_id,
                    severity_rank=severity_to_rank(verdict.severity) or 0,
                    confidence=verdict.confidence,
                    finding_type_json=(
                        normalise_finding_type(verdict.finding_type) or "[]"
                    ),
                    triage_meta=build_triage_meta(
                        confidence=verdict.confidence,
                        reasoning=verdict.reasoning,
                        remediation=verdict.remediation,
                        attack_vector=verdict.attack_vector,
                        call_stack=call_stack_str,
                        access_required=verdict.access_required,
                        exploitation_complexity=(verdict.exploitation_complexity),
                        user_interaction=verdict.user_interaction,
                    ),
                    strategy=segment,
                    triage_provider="mcp",
                    triaged_by="mcp_triage",
                    source="mcp_triage",
                )
                results.append(
                    {
                        "finding_id": finding_id,
                        "status": "accepted",
                    }
                )
                accepted_count += 1
            except VerdictParseError as exc:
                results.append(
                    {
                        "finding_id": finding_id,
                        "status": "rejected",
                        "error": str(exc),
                    }
                )
                rejected_count += 1
            except Exception as exc:
                _log.error(
                    "Unexpected error persisting verdict for finding %d: %s",
                    finding_id,
                    exc,
                )
                results.append(
                    {
                        "finding_id": finding_id,
                        "status": "rejected",
                        "error": str(exc),
                    }
                )
                rejected_count += 1

        # Determine batch status. Rejected verdicts here are parse/persist
        # failures, not "false positive" outcomes; the affected findings stay
        # untriaged and re-batch on the next fetch. The batch itself is done
        # from the server's perspective in every branch, so persist a
        # terminal status in every branch too.
        if accepted_count > 0 and rejected_count == 0:
            batch_status = "completed"
        elif accepted_count == 0 and rejected_count > 0:
            batch_status = "failed"
        else:
            batch_status = "completed"
        self._triage_repo.complete_batch(batch_id, batch_status)

        if self._event_sink:
            from domain.pipeline.triage_events import (
                BatchCompleted,
                BatchFailed,
            )

            if batch_status == "failed":
                self._event_sink.emit(
                    BatchFailed(
                        scan_run_id=run_id,
                        project_id=None,
                        batch_id=batch_id,
                        segment=segment,
                        message=f"MCP batch {batch_id} failed",
                    )
                )
            else:
                self._event_sink.emit(
                    BatchCompleted(
                        scan_run_id=run_id,
                        project_id=None,
                        batch_id=batch_id,
                        segment=segment,
                        findings_count=accepted_count,
                        message=f"MCP batch {batch_id} completed",
                    )
                )

        return {
            "results": results,
            "batch_status": batch_status,
        }

    def skip_batch(self, batch_id: int) -> dict[str, str]:
        """Mark a batch as skipped."""
        self._triage_repo.complete_batch(batch_id, "skipped")
        return {"status": "skipped"}

    def get_triage_status(self, project_name: str) -> dict[str, Any]:
        """Return triage progress for a project without claiming a batch."""
        run_id = self._run_repo.latest_run_id()
        summary = (
            self._triage_repo.summarize_for_run(run_id) if run_id is not None else None
        )
        if summary is None:
            return {
                "pending_batches": 0,
                "completed_batches": 0,
                "failed_batches": 0,
                "total_findings": 0,
                "max_concurrent_agents": self._max_concurrent_agents,
            }
        counts = summary.counts_by_status
        return {
            "pending_batches": counts.get("pending", 0),
            "completed_batches": (
                counts.get("completed", 0) + counts.get("skipped", 0)
            ),
            "failed_batches": counts.get("failed", 0),
            "total_findings": summary.total_findings,
            "max_concurrent_agents": self._max_concurrent_agents,
        }

    # Private helpers

    def _get_run_id_for_batch(self, batch_id: int) -> int:
        """Look up the run_id for a given batch_id."""
        latest = self._run_repo.latest_run_id()
        if latest is None:
            raise ValueError(f"No scan runs exist; cannot resolve batch {batch_id}")
        batches = self._triage_repo.list_for_run(latest)
        for batch in batches:
            if batch.id == batch_id:
                return batch.run_id
        raise ValueError(f"Batch {batch_id} not found in run {latest}")
