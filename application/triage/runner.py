"""Triage orchestration: TriageResult and TriageRunner."""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import LockRegistry, get_registry
from application.locking.cancellation import CancellationToken, no_op_token
from application.ports.triage_event_sink import (
    NullTriageEventSink,
    TriageEventSink,
)
from application.tools.registry import tool_registry
from core.config.manager import ConfigManager as _ConfigManager
from core.config.schemas.global_config import MCP_SESSION_TIMEOUT_SECONDS_DEFAULT
from core.project_paths import ProjectPaths
from domain.pipeline.triage_events import (
    BatchCompleted,
    BatchCreated,
    BatchFailed,
    BatchStarted,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
)

try:
    _cfg = _ConfigManager(str(Path(__file__).parent.parent.parent)).global_config
    SESSION_TIMEOUT_SECONDS: int = _cfg.mcp_session_timeout_seconds
except FileNotFoundError:
    SESSION_TIMEOUT_SECONDS = MCP_SESSION_TIMEOUT_SECONDS_DEFAULT

if TYPE_CHECKING:
    from application.ports.audit_repository import AuditRepositoryPort
    from application.ports.triage_agent import TriageAgentPort
    from infrastructure.store.repositories.runs import RunRepository
    from infrastructure.store.repositories.triage import TriageBatchRepository

_log = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).parent.parent.parent

_AUDIT_WRITE_TOOLS = ("update_finding", "update_findings_batch")


class TriageCancelled(Exception):
    """Raised when triage observes its CancellationToken set mid-run.

    The runner's batch loop catches this, marks remaining batches
    cancelled, emits a ``run_cancelled`` event, and exits cleanly.
    """


class NoScanRunError(RuntimeError):
    """Raised when triage is dispatched but the project has no scan_runs.

    Triage operates against the latest scan_run for the project. If no
    scan has ever run, there is nothing to triage. The API surface
    translates this into a 404; the REPL surfaces the message.
    """


@dataclass
class TriageResult:
    sessions_run: int
    success: int
    failed: int
    incomplete: int


class TriageRunner:
    def __init__(
        self,
        project: str,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        audit_repo: AuditRepositoryPort,
        app_root: Path,
        registry: LockRegistry | None = None,
        *,
        event_sink: TriageEventSink | None = None,
        cancel_token: CancellationToken | None = None,
        project_id: int | None = None,
        scan_run_id: int | None = None,
        triage_agent: TriageAgentPort,
    ) -> None:
        self._project = project
        self._run_repo = run_repo
        self._triage_repo = triage_repo
        self._audit_repo = audit_repo
        self._app_root = app_root
        self._registry = registry if registry is not None else get_registry()
        self._event_sink: TriageEventSink = event_sink or NullTriageEventSink()
        self._cancel_token: CancellationToken = cancel_token or no_op_token()
        self._project_id = project_id
        self._scan_run_id = scan_run_id
        self._triage_agent = triage_agent

    @classmethod
    def for_project(cls, project: str, app_root: Path | None = None) -> TriageRunner:
        root = app_root or _APP_ROOT
        paths = ProjectPaths.from_canonical(root, project)
        if not paths.findings_db.exists():
            raise FileNotFoundError(f"Project database not found: {paths.findings_db}")
        from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent
        from infrastructure.store import make_store

        run_repo, _, triage_repo, audit_repo = make_store(root, project)
        return cls(
            project,
            run_repo,
            triage_repo,
            audit_repo,
            root,
            triage_agent=ClaudeTriageAgent(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def batch(self) -> tuple[int, int]:
        """Run batching phase only.

        Resolves the scan_run_id (constructor arg, else latest in the
        project DB via ``RunRepository.latest_run_id()``), creates
        triage_batches rows for that scan_run, and returns
        ``(scan_run_id, total_batches_created)``. Raises
        :class:`NoScanRunError` if the project has no scan runs.
        """
        run_id = self._resolve_scan_run_id()

        reset_count = self._triage_repo.reset_stale_batches(run_id)
        if reset_count:
            _log.info(
                "Reset %d stale in_progress batches for run_id=%d",
                reset_count,
                run_id,
            )

        skip_tools = frozenset(
            t.name for t in tool_registry.get_all_tools() if getattr(t, "skip", False)
        )
        combos = self._triage_repo.get_active_finding_combos(skip_tools)

        total = 0
        for tool, repo, segment in combos:
            try:
                count = self._triage_repo.create_batches(run_id, tool, repo, segment)
                _log.info(
                    "Created %d batches: tool=%s repo=%s segment=%s",
                    count,
                    tool,
                    repo,
                    segment,
                )
                print(f"  Batched {count} batch(es) for {tool}/{repo}/{segment}")
                if count > 0:
                    self._emit(
                        BatchCreated(
                            scan_run_id=run_id,
                            project_id=self._project_id,
                            batch_id=0,
                            segment=segment,
                            findings_count=count,
                            message=(
                                f"Batched {count} batch(es) for {tool}/{repo}/{segment}"
                            ),
                        )
                    )
                total += count
            except Exception as exc:
                raise RuntimeError(
                    f"Batching failed for {tool}/{repo}/{segment}: {exc}"
                ) from exc
        return run_id, total

    def run(self) -> TriageResult:
        """Run full triage pipeline (batch → MCP setup → Claude sessions)."""
        run_id, _total = self.batch()
        self._emit(
            RunStarted(
                scan_run_id=run_id,
                project_id=self._project_id,
                message=f"Triage starting for scan_run_id={run_id}",
            )
        )
        holder = f"triage-run:{run_id}"
        with self._registry.job("triage", holder):
            mcp_json_path = self._write_mcp_config(run_id)
            try:
                result = self._run_batch_loop(
                    run_id,
                    lambda batch_id, render_fn, finding_ids: self._run_session(
                        render_fn, finding_ids
                    ),
                    holder_token=holder,
                )
            except TriageCancelled:
                self._triage_repo.cancel_remaining(run_id)
                self._emit(
                    RunCancelled(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        message="Triage cancelled",
                    )
                )
                raise
            except Exception as exc:
                self._emit_run_failed(run_id, exc)
                raise
            finally:
                mcp_json_path.unlink(missing_ok=True)
        self._emit(
            RunCompleted(
                scan_run_id=run_id,
                project_id=self._project_id,
                message="Triage completed",
                processed_count=result.sessions_run,
            )
        )
        return result

    def run_dry_run(self) -> int:
        """Batch phase + render prompts to DEBUG log. No MCP server, no Claude.

        Returns the number of non-skip batches processed.
        """
        run_id, _total = self.batch()

        def _handler(
            batch_id: int,
            render_fn: Callable[..., str],
            finding_ids: list[int],
        ) -> str:
            prompt_text = render_fn(finding_ids, self._project)
            _log.debug(
                "========== BATCH %d (%d findings) ==========\n%s\n"
                "========== END BATCH %d ==========",
                batch_id,
                len(finding_ids),
                prompt_text,
                batch_id,
            )
            return "success"

        result = self._run_batch_loop(run_id, _handler)
        return result.sessions_run

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_scan_run_id(self) -> int:
        """Return the scan_run_id triage will operate on.

        Constructor arg wins; otherwise the repository reports the
        latest scan_run in the project's DB. Raises
        :class:`NoScanRunError` if no scan_runs exist.
        """
        if self._scan_run_id is not None:
            return self._scan_run_id
        latest = self._run_repo.latest_run_id()
        if latest is None:
            raise NoScanRunError(
                f"No scan runs found for project {self._project!r}; "
                "run a scan before triage"
            )
        return latest

    def _emit(self, event: object) -> None:
        """Emit *event* through the configured sink, swallowing failures."""
        try:
            self._event_sink.emit(event)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - defensive
            _log.debug("Triage event sink raised; swallowing: %s", exc)

    def _check_cancelled(self) -> None:
        if self._cancel_token.is_set():
            raise TriageCancelled

    def _emit_run_failed(self, run_id: int, exc: BaseException) -> None:
        """Emit a ``triage_failed`` event before re-raising *exc*.

        Best-effort: pulls completed/total counts from
        ``summarize_for_run`` and the first finding id of the most
        recently in-progress batch for ``failed_at_finding_id``.
        ``resumable`` is True when at least one batch is still in
        ``pending`` or ``in_progress`` (i.e. the run can be resumed
        without re-batching).
        """
        completed = total = 0
        failed_at: int | None = None
        resumable = False
        try:
            summary = self._triage_repo.summarize_for_run(run_id)
            if summary is not None:
                completed = summary.processed_findings
                total = summary.total_findings
            batches = self._triage_repo.list_for_run(run_id)
            for batch in batches:
                if batch.status in ("pending", "in_progress"):
                    resumable = True
                    if failed_at is None and batch.status == "in_progress":
                        finding_ids = batch.finding_ids
                        if finding_ids:
                            failed_at = finding_ids[0]
        except Exception as inner:  # pragma: no cover - defensive
            _log.debug(
                "Failed to compute RunFailed payload for run_id=%d: %s",
                run_id,
                inner,
            )
        self._emit(
            RunFailed(
                scan_run_id=run_id,
                project_id=self._project_id,
                error=str(exc) or type(exc).__name__,
                failed_at_finding_id=failed_at,
                completed_count=completed,
                total_count=total,
                resumable=resumable,
                message="Triage failed",
            )
        )

    def _run_batch_loop(
        self,
        run_id: int,
        handler: Callable[[int, Callable[..., str], list[int]], str],
        *,
        holder_token: str | None = None,
    ) -> TriageResult:
        """Claim and process every pending batch for run_id.

        handler(batch_id, render_fn, finding_ids) -> outcome string.
        Skip-flagged tools are auto-completed without calling handler.
        When holder_token is set, finding-id locks are acquired per batch
        so that analyst PATCH requests are blocked for the duration of the
        Claude session writing those findings.
        """
        sessions_run = success = failed = incomplete = 0
        while True:
            self._check_cancelled()

            batch = self._triage_repo.claim_batch(run_id)
            if batch is None:
                break

            batch_id: int = batch["id"]
            finding_ids: list[int] = batch["finding_ids"]
            batch_data: list[dict] = batch["batch_data"]

            tool_name = batch_data[0]["tool"] if batch_data else None
            tool_obj = tool_registry.get_tool(tool_name or "") if tool_name else None

            if tool_obj is None or tool_obj.skip:
                self._triage_repo.complete_batch(batch_id, "success")
                continue

            segment = tool_obj.scan_segment
            module = importlib.import_module(
                f"application.triage.prompts.{segment}_trace"
            )
            render_fn: Callable[..., str] = module.render

            sessions_run += 1
            self._emit(
                BatchStarted(
                    scan_run_id=run_id,
                    project_id=self._project_id,
                    batch_id=batch_id,
                    segment=segment,
                    message=f"Batch {batch_id} started ({len(finding_ids)} findings)",
                )
            )
            if holder_token:
                with self._registry.findings(finding_ids, holder_token):
                    outcome = handler(batch_id, render_fn, finding_ids)
            else:
                outcome = handler(batch_id, render_fn, finding_ids)
            self._triage_repo.complete_batch(batch_id, outcome)

            if outcome == "success":
                success += 1
                self._emit(
                    BatchCompleted(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        segment=segment,
                        findings_count=len(finding_ids),
                        message=f"Batch {batch_id} completed",
                    )
                )
            elif outcome == "failed":
                failed += 1
                self._emit(
                    BatchFailed(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        segment=segment,
                        message=f"Batch {batch_id} failed",
                        error="see logs",
                    )
                )
            else:
                incomplete += 1
                self._emit(
                    BatchCompleted(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        segment=segment,
                        findings_count=len(finding_ids),
                        message=f"Batch {batch_id} {outcome}",
                    )
                )

        return TriageResult(
            sessions_run=sessions_run,
            success=success,
            failed=failed,
            incomplete=incomplete,
        )

    def _run_session(
        self, render_fn: Callable[..., str], finding_ids: list[int]
    ) -> str:
        """Run one triage-agent session.

        Returns 'success', 'failed', or 'incomplete'.
        """
        prompt_text = render_fn(finding_ids, self._project)
        session_start = datetime.now(UTC).isoformat()

        result = self._triage_agent.run_session(
            prompt_text,
            timeout_seconds=SESSION_TIMEOUT_SECONDS,
            cwd=self._app_root,
        )
        if not result.success:
            _log.error(
                "Triage session failed (rc=%d, error=%s): %s",
                result.returncode,
                result.error or "-",
                result.stderr,
            )
            return "failed"

        updated_count = self._audit_repo.count_events_since(
            _AUDIT_WRITE_TOOLS, session_start
        )
        if updated_count > 0:
            _log.info(
                "Triage session success (updates=%d)",
                updated_count,
            )
            return "success"

        _log.warning(
            "Session completed but no findings updated; "
            "possible prompt failure or empty batch"
        )
        return "incomplete"

    def _write_mcp_config(self, run_id: int) -> Path:
        """Write .mcp.json for Claude's MCP server and return its path."""
        mcp_json_path = self._app_root / ".mcp.json"
        venv_python = self._app_root / ".venv" / "bin" / "python"

        if not venv_python.exists():
            raise RuntimeError(f"Venv Python not found at {venv_python}")

        payload = {
            "mcpServers": {
                "tally-mcp": {
                    "type": "stdio",
                    "command": str(venv_python),
                    "args": [
                        "-m",
                        "tally_mcp.server",
                        "--project",
                        self._project,
                    ],
                    "env": {"TALLY_TRIAGE_RUN_ID": str(run_id)},
                    "permissions": {
                        "allow": ["get_findings_batch", "update_findings_batch"],
                        "deny": ["*"],
                    },
                }
            }
        }
        mcp_json_path.write_text(json.dumps(payload, indent=2))
        return mcp_json_path
