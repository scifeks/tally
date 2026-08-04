"""MCP triage service: core business logic for triage via MCP tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from application.triage.batching import compute_batches
from application.triage.prompts import api_trace, sast_trace
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
    from application.tools.registry import ToolRegistry


_PROMPT_RENDERERS: dict[str, Callable[..., str]] = {
    "api": api_trace.render,
    "sast": sast_trace.render,
}

_log = logging.getLogger(__name__)


class McpTriageService:
    """Orchestrate batch fetch, prompt rendering, and verdict writing for MCP.

    This service implements the three MCP triage tools: fetch_batch,
    submit_verdicts, and skip_batch. It reuses existing triage infrastructure
    through hexagonal ports and does not import from infrastructure, the
    auto-triage runner, or auto-triage orchestration.
    """

    def __init__(
        self,
        *,
        triage_repo: TriageBatchRepositoryPort,
        finding_repo: FindingRepositoryPort,
        run_repo: RunRepositoryPort,
        tool_registry: ToolRegistry,
    ) -> None:
        self._triage_repo = triage_repo
        self._finding_repo = finding_repo
        self._run_repo = run_repo
        self._tool_registry = tool_registry

    def fetch_batch(self, project_name: str) -> dict[str, Any]:
        """Fetch the next pending triage batch or compute new ones.

        Returns a dict with batch_id, run_id, segment, batch counts, and
        rendered prompts. If no batches are available, returns batch_id: None
        with a message.
        """
        latest_run_id = self._run_repo.latest_run_id()
        if latest_run_id is None:
            return {
                "batch_id": None,
                "message": f"No scan runs for project '{project_name}'",
            }

        run_id = latest_run_id

        # Try to claim a pending batch
        batch = self._triage_repo.claim_batch(run_id)

        if batch is None:
            # No pending batch; compute new ones if there are untriaged findings
            self._compute_batches_for_run(run_id)
            batch = self._triage_repo.claim_batch(run_id)

        if batch is None:
            return {
                "batch_id": None,
                "message": f"No untriaged findings for project '{project_name}'",
            }

        # Determine segment from tool in batch
        tool_name = batch.batch_data[0]["tool"] if batch.batch_data else None
        tool_obj = self._tool_registry.get_tool(tool_name or "") if tool_name else None
        segment = tool_obj.scan_segment if tool_obj else "sast"

        # Render prompts
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

        # Get batch counts for progress
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
        """Process and persist a list of verdict dicts for a batch.

        Each verdict is validated and persisted. Returns per-finding results
        and final batch status (completed, failed, or in_progress).
        """
        results = []
        accepted_count = 0
        rejected_count = 0

        # Get the batch to determine segment for strategy parameter
        all_batches = self._triage_repo.list_for_run(
            self._get_run_id_for_batch(batch_id)
        )
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

                # Persist the verdict
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
                    triage_provider="anthropic",
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

        # Determine batch status
        if accepted_count > 0 and rejected_count == 0:
            # All accepted
            batch_status = "completed"
            self._triage_repo.complete_batch(batch_id, batch_status)
        elif accepted_count == 0 and rejected_count > 0:
            # All rejected
            batch_status = "failed"
            self._triage_repo.complete_batch(batch_id, batch_status)
        else:
            # Mixed: some accepted, some rejected
            batch_status = "in_progress"

        return {
            "results": results,
            "batch_status": batch_status,
        }

    def skip_batch(self, batch_id: int) -> dict[str, str]:
        """Mark a batch as skipped."""
        self._triage_repo.complete_batch(batch_id, "skipped")
        return {"status": "skipped"}

    # -- Private helpers --

    def _compute_batches_for_run(self, run_id: int) -> None:
        """Fetch untriaged findings and compute new batches for run_id."""
        combos = self._triage_repo.get_active_finding_combos(frozenset())
        for tool, repo, segment in combos:
            findings = self._triage_repo.fetch_active_findings_for_batching(
                tool, repo, segment
            )
            if findings:
                batches = compute_batches(findings)
                self._triage_repo.create_batches(run_id, batches)

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
