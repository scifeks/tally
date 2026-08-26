"""MCP ingest service for external Claude Code scans (TAL-148).

The service persists a submitted finding and syncs it to the vector
index inline rather than dispatching through the scan pipeline bus;
the bus wraps its per-scan ChromaDB handles in a scan-worker lifecycle
that a stateless MCP request can't reuse.

``list_active_projects`` is a module-level function because it
enumerates across the project registry rather than operating on a
single project. ``McpIngestService`` is per-project, one instance per
MCP request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.mcp.duplicate_grouping import (
    GroupableFinding,
    group_duplicate_candidates,
)
from application.mcp.finding_payload import (
    FindingPayloadError,
    validate_finding_payload,
)
from application.pipeline.fingerprint import compute_fingerprint
from core.project_paths import ProjectPaths
from domain.findings.normalization import normalise_finding_for_insert

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.run_repository import RunRepositoryPort
    from application.project.registry_service import ProjectRegistryService
    from application.rag.finding_indexer import FindingIndexer
    from application.rag.knowledge_base import FindingKnowledgeBase

    RunRepoFactory = Callable[[str], RunRepositoryPort]

logger = logging.getLogger(__name__)


def list_active_projects(
    project_registry: ProjectRegistryService,
    run_repo_factory: Callable[[str], Any],
) -> list[dict[str, Any]]:
    """Return every non-archived project with its latest run id.

    Each entry: {"project_id", "project_name", "path", "latest_run_id"}.
    """
    rows = project_registry.list_active()
    result: list[dict[str, Any]] = []
    for row in rows:
        paths = ProjectPaths.from_registry_row(row)
        run_repo = run_repo_factory(str(paths.findings_db))
        latest = run_repo.latest_run_id()
        result.append(
            {
                "project_id": row.id,
                "project_name": row.name,
                "path": row.path,
                "latest_run_id": latest,
            }
        )
    return result


class McpIngestService:
    """Per-project ingest service: scan-run lifecycle and finding submit."""

    def __init__(
        self,
        *,
        finding_repo: FindingRepositoryPort,
        run_repo: RunRepositoryPort,
        indexer: FindingIndexer | None = None,
        knowledge_base: FindingKnowledgeBase | None = None,
    ) -> None:
        self._findings = finding_repo
        self._runs = run_repo
        self._indexer = indexer
        self._kb = knowledge_base

    def create_scan_run(
        self,
        project_id: int,
        repo_ids: list[str],
        *,
        tool_ids: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> dict[str, int]:
        """Open a scan_run row for an external Claude Code scan."""
        run_id = self._runs.create(
            project_id=project_id,
            repo_ids=repo_ids,
            tool_ids=tool_ids or ["claudecode"],
            domains=domains or ["llm"],
            skip_enrichment=True,
            status="running",
        )
        return {"run_id": run_id}

    def end_scan(self, project_id: int, run_id: int) -> dict[str, str]:
        """Mark a scan run finished.

        ``project_id`` matches the MCP tool signature; repos are already
        project-scoped through the connection factory.
        """
        self._runs.set_status(run_id, "done")
        self._runs.set_finished_at(run_id)
        return {"status": "done"}

    def submit_finding(
        self,
        run_id: int,
        payload: dict[str, Any],
        *,
        tool: str = "claudecode",
        domain: str = "llm",
    ) -> dict[str, Any]:
        """Submit an MCP finding and sync to vector index.

        Validates the payload, normalizes and fingerprints it, inserts it
        into the database, and syncs to the vector index if configured.

        Returns {"finding_id": <int>, "status": "accepted"} on success, or
        {"finding_id": None, "status": "rejected", "error": <message>} on
        validation failure.
        """
        try:
            validated = validate_finding_payload(payload)
        except FindingPayloadError as exc:
            return {"finding_id": None, "status": "rejected", "error": str(exc)}

        now = datetime.now(UTC).isoformat()

        raw_row: dict[str, Any] = {
            "tool": tool,
            "domain": domain,
            "segment": validated.get("segment", "sast"),
            "file": validated["file"],
            "file_path": validated["file"],
            "line_number": validated["line_number"],
            "line_start": validated["line_number"],
            "description": validated["description"],
            "severity": validated["severity"],
            "confidence": validated["confidence"],
            "cwe": validated["cwe"],
            "finding_type": validated["finding_type"],
            "rule_id": validated["rule_id"],
            "triaged_by": "claudecode",
            "triaged_at": now,
            "status": "active",
        }

        optional_fields = [
            "line_end",
            "reasoning",
            "remediation",
            "attack_vector",
            "code_snippet",
        ]
        for field in optional_fields:
            if field in validated:
                raw_row[field] = validated[field]

        meta = validated.get("meta", {})
        for key, val in meta.items():
            if key not in raw_row:
                raw_row[key] = val

        normalized = normalise_finding_for_insert(raw_row)
        fingerprint = compute_fingerprint(raw_row)
        normalized_with_fp = normalized._replace(fingerprint=fingerprint)

        self._findings.insert_findings(run_id, [normalized_with_fp], should_report=True)

        ids = self._findings.get_ids_by_fingerprints([fingerprint], run_id=run_id)
        finding_id = ids[0] if ids else None

        if finding_id and self._indexer and self._kb:
            try:
                self._indexer.index_findings(
                    self._kb, [finding_id], caller_label="McpIngestService"
                )
            except Exception as exc:
                logger.exception(
                    "McpIngestService: vector index sync failed for finding_id=%s: %s",
                    finding_id,
                    exc,
                )

        return {"finding_id": finding_id, "status": "accepted"}

    def get_duplicate_candidates(self, run_id: int) -> dict[str, Any]:
        """Return candidate duplicate groups for a run.

        Grouping rule: same file, same ``rule_id``, and line ranges
        that overlap or fall within 10 lines of each other.
        """
        findings = self._findings.get_findings_by_run_id(run_id)
        groupables = [
            GroupableFinding(
                id=f.id,
                file=f.file,
                rule_id=f.rule_id,
                line_start=f.meta.get("line_number"),
                line_end=f.meta.get("line_end") or f.meta.get("line_number"),
            )
            for f in findings
        ]
        groups = group_duplicate_candidates(groupables, proximity=10)
        return {"groups": groups}

    def resolve_duplicates(
        self,
        run_id: int,
        survivor_id: int,
        removed_ids: list[int],
    ) -> dict[str, Any]:
        """Mark each removed finding as a duplicate of the survivor.

        Rejects when the survivor is missing, itself a duplicate, or
        belongs to a different run. The read-path filter only walks one
        level of ``duplicate_of``, so chains would leave losers visible.
        """
        survivor = self._findings.get_finding(survivor_id)
        if survivor is None:
            return {"status": "rejected", "error": "survivor not found"}
        if survivor.run_id != run_id:
            return {
                "status": "rejected",
                "error": "survivor does not belong to this run",
            }
        if survivor.duplicate_of is not None:
            return {
                "status": "rejected",
                "error": "survivor is already marked as a duplicate",
            }
        for loser_id in removed_ids:
            loser = self._findings.get_finding(loser_id)
            if loser is None or loser.run_id != run_id:
                continue
            self._findings.mark_as_duplicate(loser_id, survivor_id)
        return {"status": "resolved", "count": len(removed_ids)}
