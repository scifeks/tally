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

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

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
from domain.scans.vuln_scanner_registry import (
    UnknownScannerSkill,
    resolve_full_slug,
)

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.scan_event_sink import ScanEventSink
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
        scan_event_sink: ScanEventSink | None = None,
    ) -> None:
        self._findings = finding_repo
        self._runs = run_repo
        self._indexer = indexer
        self._kb = knowledge_base
        self._scan_event_sink = scan_event_sink

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

        Returns {"finding_id": <int>, "status": "accepted"} on success, or
        {"finding_id": None, "status": "rejected", "error": <message>} on
        validation failure.
        """
        try:
            validated = validate_finding_payload(payload)
        except FindingPayloadError as exc:
            return {"finding_id": None, "status": "rejected", "error": str(exc)}

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

    def set_scan_config(
        self,
        project: str | None,
        run_id: int,
        only: list[str] | None,
        exclude: list[str] | None,
        adversarial_verification: bool,
    ) -> dict[str, Any]:
        """Write scan configuration for a run.

        Validates that only and exclude are mutually exclusive and that
        every display slug resolves via the registry. Returns resolved
        full slugs.
        """
        from domain.scans.vuln_scanner_registry import resolve_display_slug

        if only and exclude:
            raise ValueError("only and exclude are mutually exclusive.")

        resolved_only = [resolve_display_slug(s) for s in (only or [])]
        resolved_exclude = [resolve_display_slug(s) for s in (exclude or [])]

        self._runs.upsert_scan_config(
            run_id=run_id,
            only_full_slugs=resolved_only,
            exclude_full_slugs=resolved_exclude,
            adversarial_verification=adversarial_verification,
        )

        return {
            "ok": True,
            "resolved_only_full_slugs": resolved_only,
            "resolved_exclude_full_slugs": resolved_exclude,
        }

    def get_scan_config(
        self,
        project: str | None,
        run_id: int,
    ) -> dict[str, Any]:
        """Read scan configuration for a run.

        Converts stored full slugs back to display slugs. Returns
        is_configured=False when no config exists.
        """
        config = self._runs.get_scan_config(run_id)

        if config is None:
            return {
                "is_configured": False,
                "only": [],
                "exclude": [],
                "adversarial_verification": False,
            }

        only_full_slugs, exclude_full_slugs, adversarial_verification = config

        only_display = []
        for s in only_full_slugs:
            try:
                only_display.append(resolve_full_slug(s))
            except UnknownScannerSkill:
                logger.warning("Stale scan slug filtered from config: %r", s)

        exclude_display = []
        for s in exclude_full_slugs:
            try:
                exclude_display.append(resolve_full_slug(s))
            except UnknownScannerSkill:
                logger.warning("Stale scan slug filtered from config: %r", s)

        return {
            "is_configured": True,
            "only": only_display,
            "exclude": exclude_display,
            "adversarial_verification": adversarial_verification,
        }

    def start_scan_phase(
        self,
        project: str | None,
        run_id: int,
        phase: str,
        usage_pool: str | None = None,
    ) -> dict[str, Any]:
        """Insert an in_progress phase execution row.

        Computes attempt_number from the max existing attempt for
        (run_id, phase) + 1. Returns {"ok": True, "execution_id": <id>,
        "attempt_number": <int>}.
        """
        conn_factory = cast(Any, self._runs)._factory
        with conn_factory.connect() as conn:
            row = conn.execute(
                "SELECT MAX(attempt_number) FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = ?",
                (run_id, phase),
            ).fetchone()
            attempt_number = (row[0] or 0) + 1

            now = datetime.now(UTC).isoformat()
            cur = conn.execute(
                "INSERT INTO scan_phase_executions"
                " (run_id, phase, attempt_number, status, usage_pool,"
                " started_at, finished_at)"
                " VALUES (?, ?, ?, 'in_progress', ?, ?, NULL)",
                (run_id, phase, attempt_number, usage_pool, now),
            )
            if cur.lastrowid is None:
                raise RuntimeError("INSERT failed to return lastrowid")
            execution_id = cur.lastrowid

        if self._scan_event_sink is not None:
            try:
                from domain.pipeline.scan_events import PhaseStarted

                self._scan_event_sink.emit(
                    PhaseStarted(
                        run_id=run_id,
                        project_id=None,
                        phase=phase,
                        attempt_number=attempt_number,
                        usage_pool=usage_pool or "",
                    )
                )
            except Exception:
                logger.warning("scan event sink emit failed", exc_info=True)

        return {
            "ok": True,
            "execution_id": execution_id,
            "attempt_number": attempt_number,
        }

    def mark_scan_phase_complete(
        self,
        project: str | None,
        run_id: int,
        phase: str,
        status: Literal["completed", "failed", "rate_limited"] = "completed",
        usage_pool: Literal["plan", "api"] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write a scan_phase_executions row for a phase.

        Auto-computes attempt_number by reading the max existing attempt
        for (run_id, phase) and adding 1. Returns {"ok": True, "execution_id": <id>,
        "attempt_number": <int>}.
        """
        if status not in ("completed", "failed", "rate_limited"):
            raise ValueError(
                f"status must be completed/failed/rate_limited, got {status!r}"
            )
        if usage_pool is not None and usage_pool not in ("plan", "api"):
            raise ValueError(f"usage_pool must be plan/api or None, got {usage_pool!r}")

        conn_factory = cast(Any, self._runs)._factory
        with conn_factory.connect() as conn:
            row = conn.execute(
                "SELECT id, attempt_number FROM scan_phase_executions"
                " WHERE run_id = ? AND phase = ? AND status = 'in_progress'"
                " ORDER BY attempt_number DESC LIMIT 1",
                (run_id, phase),
            ).fetchone()

            now = datetime.now(UTC).isoformat()
            metadata_json = json.dumps(metadata or {})

            if row is not None:
                attempt_number = row["attempt_number"]
                conn.execute(
                    "UPDATE scan_phase_executions"
                    " SET status = ?, usage_pool = ?, finished_at = ?,"
                    " metadata_json = ?"
                    " WHERE id = ?",
                    (status, usage_pool, now, metadata_json, row["id"]),
                )
                execution_id = row["id"]
            else:
                # No preceding start_scan_phase call. Fall back to INSERT
                # so the shape of the response stays consistent.
                prev = conn.execute(
                    "SELECT MAX(attempt_number) FROM scan_phase_executions"
                    " WHERE run_id = ? AND phase = ?",
                    (run_id, phase),
                ).fetchone()
                attempt_number = (prev[0] or 0) + 1
                cur = conn.execute(
                    "INSERT INTO scan_phase_executions"
                    " (run_id, phase, attempt_number, status, usage_pool,"
                    "  started_at, finished_at, metadata_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        phase,
                        attempt_number,
                        status,
                        usage_pool,
                        now,
                        now,
                        metadata_json,
                    ),
                )
                if cur.lastrowid is None:
                    raise RuntimeError("INSERT failed to return lastrowid")
                execution_id = cur.lastrowid

        if self._scan_event_sink is not None:
            try:
                meta = metadata or {}
                self._emit_phase_event(
                    status=status,
                    run_id=run_id,
                    phase=phase,
                    attempt_number=attempt_number,
                    usage_pool=usage_pool or "",
                    findings_count=meta.get("findings_count", 0),
                    error_class=meta.get("error_class", ""),
                )
            except Exception:
                logger.warning("scan event sink emit failed", exc_info=True)

        return {
            "ok": True,
            "execution_id": execution_id,
            "attempt_number": attempt_number,
        }

    def get_scan_phase_status(
        self,
        project: str | None,
        run_id: int,
    ) -> dict[str, Any]:
        """Read phase execution status for a run.

        Returns the latest attempt per phase. Completed phases are listed
        separately. Returns:
        {
            "completed_phases": [<phase>, ...],
            "latest_execution_per_phase": {
                <phase>: {"status", "usage_pool", "started_at"},
                ...
            }
        }
        """
        conn_factory = cast(Any, self._runs)._factory
        with conn_factory.connect() as conn:
            rows = conn.execute(
                "SELECT phase, status, usage_pool, started_at,"
                " MAX(attempt_number) as max_attempt"
                " FROM scan_phase_executions"
                " WHERE run_id = ?"
                " GROUP BY phase",
                (run_id,),
            ).fetchall()

        completed_phases = [r["phase"] for r in rows if r["status"] == "completed"]
        latest_execution_per_phase = {
            r["phase"]: {
                "status": r["status"],
                "usage_pool": r["usage_pool"],
                "started_at": r["started_at"],
            }
            for r in rows
        }

        return {
            "completed_phases": completed_phases,
            "latest_execution_per_phase": latest_execution_per_phase,
        }

    def mark_in_progress_failed(
        self,
        *,
        run_id: int,
        error_class: str,
    ) -> None:
        """Flip every in_progress phase execution for a run to failed.

        Called by ScanBackgroundLauncher on crash to avoid leaving
        phantom in_progress rows that would trigger spurious resumes.
        """
        now = datetime.now(UTC).isoformat()
        conn_factory = cast(Any, self._runs)._factory
        with conn_factory.connect() as conn:
            flipped = conn.execute(
                "UPDATE scan_phase_executions"
                " SET status = 'failed', finished_at = ?, error_class = ?"
                " WHERE run_id = ? AND status = 'in_progress'"
                " RETURNING phase, attempt_number, usage_pool",
                (now, error_class, run_id),
            ).fetchall()

        if self._scan_event_sink is None:
            return
        for row in flipped:
            self._emit_phase_event(
                status="failed",
                run_id=run_id,
                phase=row["phase"],
                attempt_number=row["attempt_number"],
                usage_pool=row["usage_pool"] or "",
                findings_count=0,
                error_class=error_class,
            )

    def _emit_phase_event(
        self,
        *,
        status: str,
        run_id: int,
        phase: str,
        attempt_number: int,
        usage_pool: str,
        findings_count: int,
        error_class: str,
    ) -> None:
        """Emit the appropriate phase event based on status."""
        from domain.pipeline.scan_events import (
            PhaseCompleted,
            PhaseFailed,
            PhaseRateLimited,
        )

        if self._scan_event_sink is None:
            return

        if status == "completed":
            self._scan_event_sink.emit(
                PhaseCompleted(
                    run_id=run_id,
                    project_id=None,
                    phase=phase,
                    attempt_number=attempt_number,
                    usage_pool=usage_pool,
                    findings_count=findings_count,
                )
            )
        elif status == "failed":
            self._scan_event_sink.emit(
                PhaseFailed(
                    run_id=run_id,
                    project_id=None,
                    phase=phase,
                    attempt_number=attempt_number,
                    usage_pool=usage_pool,
                    error_class=error_class,
                )
            )
        elif status == "rate_limited":
            self._scan_event_sink.emit(
                PhaseRateLimited(
                    run_id=run_id,
                    project_id=None,
                    phase=phase,
                    attempt_number=attempt_number,
                    usage_pool=usage_pool,
                )
            )
