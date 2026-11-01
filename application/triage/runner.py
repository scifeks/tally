"""Triage orchestration: TriageResult and TriageRunner."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.locking import LockRegistry, get_registry
from application.locking.cancellation import CancellationToken, no_op_token
from application.ports.triage_agent import TriageBackendUnavailable
from application.ports.triage_event_sink import (
    NullTriageEventSink,
    TriageEventSink,
)
from application.tools.registry import ToolRegistry
from application.triage.batch_creator import create_triage_batches
from application.triage.prompts import dast_trace, sast_trace
from application.triage.verdict import (
    SourceNotExaminedError,
    Verdict,
    VerdictParseError,
)
from domain.findings.normalization import (
    build_triage_meta,
    normalise_finding_type,
    severity_to_rank,
)
from domain.pipeline.triage_events import (
    BatchAttemptCompleted,
    BatchAttemptFailed,
    BatchAttemptRateLimited,
    BatchAttemptStarted,
    BatchCompleted,
    BatchFailed,
    BatchStarted,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunRateLimited,
    RunStarted,
    TriageEvent,
)
from infrastructure.anthropic.error_classifier import ErrorClass

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_agent import OneshotTriageBackendPort
    from application.ports.triage_batch_repository import TriageBatchRepositoryPort
    from application.triage.factory import (
        ResolvedTriageConfig,
        TriageAgentFactory,
    )


_PROMPT_RENDERERS: dict[str, Callable[..., str]] = {
    "sast": sast_trace.render,
    "web": dast_trace.render,
}

_log = logging.getLogger(__name__)


class TriageCancelled(Exception):
    """Raised when triage observes its CancellationToken set mid-run."""


class TriageAborted(Exception):
    """Raised when the backend transport dies mid-run.

    Propagates out of the batch loop so remaining pending batches stay
    ``pending`` (resumable) instead of every one being marked ``failed``.

    Carries ``error_class`` from the originating
    ``TriageBackendUnavailable`` so the batch loop can persist it on the
    execution row before re-raising.
    """

    def __init__(self, *args: object, error_class: str | None = None) -> None:
        super().__init__(*args)
        self.error_class = error_class


class NoScanRunError(RuntimeError):
    """Raised when triage is dispatched but the project has no scan_runs."""


@dataclass
class TriageResult:
    sessions_run: int
    success: int
    failed: int
    incomplete: int
    status: str = "completed"
    last_error_class: str | None = None


class TriageRunner:
    def __init__(
        self,
        project: str,
        run_repo: RunRepositoryPort,
        triage_repo: TriageBatchRepositoryPort,
        audit_repo: object | None,
        app_root: Path,
        registry: LockRegistry | None = None,
        *,
        event_sink: TriageEventSink | None = None,
        cancel_token: CancellationToken | None = None,
        project_id: int | None = None,
        scan_run_id: int | None = None,
        triage_backend: OneshotTriageBackendPort,
        session_timeout_seconds: int,
        retry_count: int = 1,
        tool_registry: ToolRegistry,
        finding_repo: FindingRepositoryPort | None = None,
        repo_paths: dict[str, Path] | None = None,
        triage_provider: str,
        triaged_by: str = "auto_triage",
        debug: bool = False,
        max_findings_per_batch: int = 4,
        billing_method: str | None = None,
        agent_factory: TriageAgentFactory | None = None,
        resolved_config: ResolvedTriageConfig | None = None,
        enable_auto_failover: bool = False,
        api_key_available: bool = False,
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
        self._triage_backend = triage_backend
        self._session_timeout_seconds = session_timeout_seconds
        self._retry_count = retry_count
        self._tool_registry = tool_registry
        self._finding_repo = finding_repo
        self._repo_paths: dict[str, Path] = repo_paths or {}
        self._triage_provider = triage_provider
        self._triaged_by = triaged_by
        self._debug = debug
        self._max_findings_per_batch = max_findings_per_batch
        self._billing_method = billing_method
        self._agent_factory = agent_factory
        self._resolved_config = resolved_config
        self._enable_auto_failover = enable_auto_failover
        self._api_key_available = api_key_available

        self._current_run_id: int = 0
        self._current_attempt_number: int = 1

        self.result: TriageResult | None = None

    # Public API

    def batch(self) -> tuple[int, int]:
        """Run batching phase only.

        Raises NoScanRunError if the project has no scan runs.
        """
        run_id = self._resolve_scan_run_id()
        created = create_triage_batches(
            run_id=run_id,
            triage_repo=self._triage_repo,
            tool_registry=self._tool_registry,
            max_findings_per_batch=self._max_findings_per_batch,
            event_sink=self._event_sink,
            project_id=self._project_id,
        )
        return run_id, len(created)

    def run(
        self,
        *,
        holder_token: str | None = None,
        skip_batching: bool = False,
    ) -> TriageResult:
        """Runs one triage pass for a scan run.

        When ``skip_batching`` is True the batching phase is skipped and
        the claim loop processes whatever pending batches already exist.
        Used by the resume path where ``reset_for_resume`` has already
        flipped retryable batches back to pending.
        """
        if skip_batching:
            run_id = self._resolve_scan_run_id()
        else:
            run_id, _total = self.batch()
        self._emit(
            RunStarted(
                scan_run_id=run_id,
                project_id=self._project_id,
                message=f"Triage starting for scan_run_id={run_id}",
            )
        )
        try:
            with self._prepare_session(run_id) as prepared:
                result = self._run_batch_loop(
                    run_id,
                    lambda bid, bd, seg: self._run_batch_findings(
                        bid, bd, seg, cwd=prepared.cwd
                    ),
                    holder_token=holder_token,
                )
        except TriageCancelled:
            self._triage_repo.cancel_remaining(run_id)
            self._emit(
                RunCancelled(
                    scan_run_id=run_id,
                    project_id=self._project_id,
                    message="Triage canceled",
                )
            )
            raise
        except Exception as exc:
            self._emit_run_failed(run_id, exc)
            raise

        self.result = result

        if result.status == "rate_limited":
            pass  # RunRateLimited already emitted in _run_batch_loop
        elif result.failed > 0 and result.success == 0:
            self._emit(
                RunFailed(
                    scan_run_id=run_id,
                    project_id=self._project_id,
                    error="All batches failed",
                    completed_count=0,
                    total_count=result.sessions_run,
                    resumable=True,
                    message=("Triage completed with all batches failing"),
                )
            )
        else:
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
        """Logs prompts without running the triage backend."""
        run_id, _total = self.batch()

        def _handler(
            batch_id: int,
            batch_data: list[dict[str, Any]],
            segment: str,
        ) -> str:
            render_fn = _PROMPT_RENDERERS[segment]
            for finding in batch_data:
                fid = finding.get("id", "?")
                prompt = render_fn(
                    finding,
                    project=self._project,
                )
                _log.debug(
                    "========== FINDING %s (batch %d)"
                    " ==========\n%s\n"
                    "========== END FINDING %s ==========",
                    fid,
                    batch_id,
                    prompt,
                    fid,
                )
            return "success"

        result = self._run_batch_loop(run_id, _handler)
        return result.sessions_run

    # Private helpers

    def _resolve_scan_run_id(self) -> int:
        """Return the scan_run_id triage will operate on."""
        if self._scan_run_id is not None:
            return self._scan_run_id
        latest = self._run_repo.latest_run_id()
        if latest is None:
            raise NoScanRunError(
                f"No scan runs found for project {self._project!r}; "
                "run a scan before triage"
            )
        return latest

    def _emit(self, event: TriageEvent) -> None:
        """Emit *event* through the configured sink, swallowing failures."""
        try:
            self._event_sink.emit(event)
        except Exception as exc:  # pragma: no cover - defensive
            _log.debug("Triage event sink raised; swallowing: %s", exc)

    def _check_canceled(self) -> None:
        if self._cancel_token.is_set():
            raise TriageCancelled

    def _emit_run_failed(self, run_id: int, exc: BaseException) -> None:
        """Emit a RunFailed event with best-effort progress counts."""
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
        handler: Callable[[int, list[dict[str, Any]], str], str],
        *,
        holder_token: str | None = None,
    ) -> TriageResult:
        """Claim and process every pending batch for run_id.

        Acquires per-finding locks when holder_token is set so analyst
        writes are blocked during agent processing.
        """
        sessions_run = success = failed = incomplete = 0
        abort_status: str | None = None
        abort_error_class: str | None = None

        while True:
            self._check_canceled()

            batch = self._triage_repo.claim_batch(
                run_id, usage_pool=self._billing_method
            )
            if batch is None:
                break

            batch_id = batch.id
            finding_ids = batch.finding_ids
            batch_data = batch.batch_data
            attempt_number = batch.attempt_number or 1

            tool_name = batch_data[0]["tool"] if batch_data else None
            tool_obj = (
                self._tool_registry.get_tool(tool_name or "") if tool_name else None
            )

            if tool_obj is None or tool_obj.skip:
                self._emit(
                    BatchAttemptStarted(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        attempt_number=attempt_number,
                        usage_pool=self._billing_method or "plan",
                        message=(
                            f"Batch {batch_id} attempt "
                            f"{attempt_number} started (skipped)"
                        ),
                    )
                )
                self._emit(
                    BatchAttemptCompleted(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        attempt_number=attempt_number,
                        usage_pool=self._billing_method or "plan",
                        message=(
                            f"Batch {batch_id} attempt "
                            f"{attempt_number} completed (skipped)"
                        ),
                    )
                )
                self._triage_repo.complete_batch(batch_id, "completed")
                continue

            segment = tool_obj.scan_segment

            sessions_run += 1
            self._current_run_id = run_id
            self._current_attempt_number = attempt_number
            self._emit(
                BatchAttemptStarted(
                    scan_run_id=run_id,
                    project_id=self._project_id,
                    batch_id=batch_id,
                    attempt_number=attempt_number,
                    usage_pool=self._billing_method or "",
                    message=f"Batch {batch_id} attempt {attempt_number} started",
                )
            )
            self._emit(
                BatchStarted(
                    scan_run_id=run_id,
                    project_id=self._project_id,
                    batch_id=batch_id,
                    segment=segment,
                    message=(f"Batch {batch_id} started ({len(finding_ids)} findings)"),
                )
            )
            try:
                if holder_token:
                    with self._registry.findings(finding_ids, holder_token):
                        outcome = handler(batch_id, batch_data, segment)
                else:
                    outcome = handler(batch_id, batch_data, segment)
            except TriageAborted as exc:
                ec_str = exc.error_class
                is_rate_limit = ec_str in (
                    ErrorClass.RATE_LIMIT_PLAN.value,
                    ErrorClass.RATE_LIMIT_API.value,
                )
                if is_rate_limit:
                    self._emit(
                        BatchAttemptRateLimited(
                            scan_run_id=run_id,
                            project_id=self._project_id,
                            batch_id=batch_id,
                            attempt_number=attempt_number,
                            usage_pool=self._billing_method or "",
                            message=(
                                f"Batch {batch_id} attempt "
                                f"{attempt_number} rate limited"
                            ),
                        )
                    )
                else:
                    self._emit(
                        BatchAttemptFailed(
                            scan_run_id=run_id,
                            project_id=self._project_id,
                            batch_id=batch_id,
                            attempt_number=attempt_number,
                            usage_pool=self._billing_method or "",
                            message=f"Batch {batch_id} attempt {attempt_number} failed",
                            error=ec_str or "",
                        )
                    )
                self._triage_repo.complete_batch(
                    batch_id,
                    "rate_limited" if is_rate_limit else "failed",
                    error_class=ec_str,
                )
                failed += 1
                abort_status = "rate_limited" if is_rate_limit else "failed"
                abort_error_class = ec_str
                if is_rate_limit:
                    self._emit(
                        RunRateLimited(
                            scan_run_id=run_id,
                            project_id=self._project_id,
                            usage_pool=self._billing_method or "",
                            message=f"Rate limited ({ec_str})",
                        )
                    )
                break

            attempt_number = self._current_attempt_number

            db_status = "failed" if outcome == "failed" else "completed"
            self._triage_repo.complete_batch(batch_id, db_status)

            if outcome == "success":
                success += 1
                self._emit(
                    BatchAttemptCompleted(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        attempt_number=attempt_number,
                        usage_pool=self._billing_method or "",
                        message=f"Batch {batch_id} attempt {attempt_number} completed",
                    )
                )
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
                    BatchAttemptFailed(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        attempt_number=attempt_number,
                        usage_pool=self._billing_method or "",
                        message=f"Batch {batch_id} attempt {attempt_number} failed",
                        error="see logs",
                    )
                )
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
                    BatchAttemptCompleted(
                        scan_run_id=run_id,
                        project_id=self._project_id,
                        batch_id=batch_id,
                        attempt_number=attempt_number,
                        usage_pool=self._billing_method or "",
                        message=f"Batch {batch_id} attempt {attempt_number} {outcome}",
                    )
                )
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

        result = TriageResult(
            sessions_run=sessions_run,
            success=success,
            failed=failed,
            incomplete=incomplete,
        )
        if abort_status is not None:
            result.status = abort_status
            result.last_error_class = abort_error_class
        return result

    def _can_failover(self, error_class: object) -> bool:
        """True when plan-to-api failover is allowed for this error."""
        return (
            error_class == ErrorClass.RATE_LIMIT_PLAN
            and self._enable_auto_failover
            and self._api_key_available
            and self._billing_method != "api"
            and self._agent_factory is not None
            and self._resolved_config is not None
        )

    def _execute_failover(self, batch_id: int) -> int:
        """Swap the triage backend from plan to api billing.

        Updates ``self._current_attempt_number`` so the batch loop reports
        the new attempt on its ``BatchAttemptCompleted``. Returns the new
        execution id.
        """
        _log.info("Rate limited on plan billing; failing over to api")
        self._emit(
            BatchAttemptRateLimited(
                scan_run_id=self._current_run_id,
                project_id=self._project_id,
                batch_id=batch_id,
                attempt_number=self._current_attempt_number,
                usage_pool=self._billing_method or "",
                message=(
                    f"Batch {batch_id} attempt "
                    f"{self._current_attempt_number} rate limited"
                ),
            )
        )
        new_exec_id, new_attempt = self._triage_repo.start_failover_execution(
            batch_id, "api"
        )
        self._billing_method = "api"
        assert self._resolved_config is not None
        assert self._agent_factory is not None
        api_config = replace(self._resolved_config, billing_method="api")
        self._triage_backend = self._agent_factory.create(api_config)
        self._emit(
            BatchAttemptStarted(
                scan_run_id=self._current_run_id,
                project_id=self._project_id,
                batch_id=batch_id,
                attempt_number=new_attempt,
                usage_pool=self._billing_method,
                message=f"Batch {batch_id} attempt {new_attempt} started",
            )
        )
        self._current_attempt_number = new_attempt
        return new_exec_id

    def _run_batch_findings(
        self,
        batch_id: int,
        batch_data: list[dict[str, Any]],
        segment: str,
        *,
        cwd: Path,
    ) -> str:
        """Triage each finding in the batch via the one-shot adapter.

        Returns 'success' (all ok), 'failed' (all failed), or
        'incomplete' (mixed).
        """
        render_fn = _PROMPT_RENDERERS[segment]
        succeeded = 0
        total = len(batch_data)
        max_attempts = self._retry_count + 1

        for finding in batch_data:
            self._check_canceled()
            fid = finding.get("id", -1)
            prompt = render_fn(finding, project=self._project)
            ok = False
            for attempt in range(max_attempts):
                try:
                    verdict = self._triage_backend.run_triage(
                        prompt,
                        finding_id=fid,
                        timeout_seconds=self._session_timeout_seconds,
                        cwd=cwd,
                    )
                    if self._debug:
                        raw = getattr(
                            self._triage_backend,
                            "last_raw_output",
                            "",
                        )
                        if raw:
                            self._write_debug_log(batch_id, fid, raw)
                    self._write_verdict(verdict, segment)
                    ok = True
                    break
                except SourceNotExaminedError as exc:
                    _log.warning(
                        "Finding %d in batch %d: source not examined"
                        " (%s); skipping update",
                        fid,
                        batch_id,
                        exc.reason,
                    )
                    break
                except VerdictParseError as exc:
                    self._log_verdict_failure(batch_id, fid, exc)
                    if attempt < max_attempts - 1:
                        _log.warning(
                            "Retrying finding %d (attempt %d/%d)",
                            fid,
                            attempt + 2,
                            max_attempts,
                        )
                        continue
                except TriageBackendUnavailable as exc:
                    stderr_tail = getattr(self._triage_backend, "last_relay_stderr", "")
                    _log.error(
                        "Triage backend unavailable at finding %d in batch %d: %s",
                        fid,
                        batch_id,
                        exc,
                    )
                    self._write_error_log(
                        batch_id,
                        fid,
                        exc_type=type(exc).__name__,
                        exc_message=str(exc),
                        stderr_tail=stderr_tail,
                    )
                    ec = exc.error_class
                    if self._can_failover(ec):
                        self._execute_failover(batch_id)
                        ok = self._retry_finding_after_failover(
                            prompt, fid, batch_id, segment, cwd=cwd
                        )
                        break
                    ec_str = getattr(ec, "value", None) or (str(ec) if ec else None)
                    raise TriageAborted(str(exc), error_class=ec_str) from exc
                except Exception as exc:
                    _log.error(
                        "Triage failed for finding %d in batch %d: %s: %s",
                        fid,
                        batch_id,
                        type(exc).__name__,
                        exc,
                    )
                    stderr_tail = getattr(self._triage_backend, "last_relay_stderr", "")
                    self._write_error_log(
                        batch_id,
                        fid,
                        exc_type=type(exc).__name__,
                        exc_message=str(exc),
                        stderr_tail=stderr_tail,
                    )
                    break
            if ok:
                succeeded += 1

        if succeeded == total:
            return "success"
        if succeeded == 0:
            return "failed"
        return "incomplete"

    def _retry_finding_after_failover(
        self,
        prompt: str,
        finding_id: int,
        batch_id: int,
        segment: str,
        *,
        cwd: Path,
    ) -> bool:
        """Retry a single finding on the newly-swapped API backend.

        Returns True if the finding was triaged successfully. Raises
        TriageAborted if the API backend also fails.
        """
        try:
            verdict = self._triage_backend.run_triage(
                prompt,
                finding_id=finding_id,
                timeout_seconds=self._session_timeout_seconds,
                cwd=cwd,
            )
            self._write_verdict(verdict, segment)
            return True
        except TriageBackendUnavailable as retry_exc:
            _log.error(
                "API backend also unavailable at finding %d in batch %d: %s",
                finding_id,
                batch_id,
                retry_exc,
            )
            retry_ec = retry_exc.error_class
            ec_str = getattr(retry_ec, "value", None) or (
                str(retry_ec) if retry_ec else None
            )
            raise TriageAborted(str(retry_exc), error_class=ec_str) from retry_exc

    def _log_verdict_failure(
        self,
        batch_id: int,
        fid: int,
        exc: VerdictParseError,
    ) -> None:
        _log.warning(
            "Verdict parse failed for finding %d in batch %d: %s",
            fid,
            batch_id,
            exc.problem,
        )
        raw = getattr(self._triage_backend, "last_raw_output", "")
        content = raw or exc.raw_output
        if self._debug and content:
            self._write_debug_log(batch_id, fid, content)
        if not content:
            stderr_tail = getattr(self._triage_backend, "last_relay_stderr", "")
            self._write_error_log(
                batch_id,
                fid,
                exc_type=type(exc).__name__,
                exc_message=f"{exc.problem} (raw_output empty)",
                stderr_tail=stderr_tail,
            )

    def _write_debug_log(self, batch_id: int, finding_id: int, raw_output: str) -> None:
        from datetime import datetime

        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        log_dir = self._app_root / "logs" / "triage"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{batch_id}-{finding_id}-{ts}.log"
        path.write_text(raw_output, encoding="utf-8")
        _log.debug("Triage debug log written to %s", path)

    def _write_error_log(
        self,
        batch_id: int,
        finding_id: int,
        *,
        exc_type: str,
        exc_message: str,
        stderr_tail: str,
    ) -> None:
        """Always-on diagnostic dump for failures the runner cannot explain.

        Fires regardless of ``self._debug`` because these files exist
        precisely for the case where the run log line is not enough to
        tell what the backend did.
        """
        from datetime import datetime

        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        log_dir = self._app_root / "logs" / "triage"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{batch_id}-{finding_id}-{ts}.err.log"
        body = (
            f"exception_type: {exc_type}\n"
            f"exception_message: {exc_message}\n"
            f"---\nrelay_stderr_tail:\n{stderr_tail}\n"
        )
        path.write_text(body, encoding="utf-8")
        _log.debug("Triage error log written to %s", path)

    def _write_verdict(self, verdict: Verdict, segment: str) -> None:
        if self._finding_repo is None:
            raise RuntimeError("finding_repo not configured on TriageRunner")
        call_stack_str = json.dumps(verdict.call_stack) if verdict.call_stack else None
        self._finding_repo.update_finding(
            verdict.finding_id,
            severity_rank=severity_to_rank(verdict.severity) or 0,
            confidence=verdict.confidence,
            finding_type_json=normalise_finding_type(verdict.finding_type) or "[]",
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
            triage_provider=self._triage_provider,
            triaged_by=self._triaged_by,
            source="auto_triage",
        )

    def _prepare_session(self, run_id: int):
        return self._triage_backend.prepare_session(
            project=self._project,
            run_id=run_id,
            app_root=self._app_root,
        )
