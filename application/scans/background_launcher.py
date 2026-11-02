"""Spawn an Agent SDK session that runs /tally-scan-external.

The minted token is passed as a Bearer header on the MCP server config so the
SDK session authenticates against the running Tally MCP server. Tokens are
tagged ``scan-background-<run_id>`` and left to expire naturally.

The session runs inside the Docker sandbox and reaches the host MCP server via
host.docker.internal; the host only consumes typed relay events.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any, Literal, Protocol

from application.triage.compose import COMPOSE_RELATIVE_PATH
from factories.persistence import load_active_repos
from infrastructure.anthropic.error_classifier import classify
from infrastructure.anthropic.sdk_relay.client import SDKRelayClient
from infrastructure.anthropic.sdk_relay.events import (
    AssistantTextEvent,
    ErrorEvent,
    ResultEvent,
)
from infrastructure.anthropic.sdk_relay.job_spec import ScanJobSpec

if TYPE_CHECKING:
    from application.anthropic.mode_availability import (
        BackgroundModeAvailabilityService,
    )
    from application.ports.scan_event_sink import ScanEventSink

_log = logging.getLogger(__name__)

_SDK_TIMEOUT_SECONDS = 3600

_SCAN_ALLOWED_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "Task",
    "WebFetch",
    "mcp__tally__*",
)


class ScanConfigurationError(ValueError):
    """Raised when the scan cannot proceed due to project misconfiguration."""


class ScanPhaseCleanupPort(Protocol):
    """Cleanup hook for marking in-progress phases as failed on crash."""

    def mark_in_progress_failed(self, *, run_id: int, error_class: str) -> None: ...


class ScanRunStatusPort(Protocol):
    """Writes terminal status to the scan_runs row after SDK exit."""

    def set_status(self, run_id: int, status: str) -> None: ...

    def set_status_if_in(
        self, run_id: int, status: str, allowed_current: tuple[str, ...]
    ) -> bool: ...


class _SDKRuntimeError(RuntimeError):
    """Carries status_code from SDK ResultMessage errors for the classifier."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


_RESUMABLE_STATUSES = frozenset({"in_progress", "failed", "rate_limited"})


def _needs_resume(latest_execution_per_phase: dict[str, dict[str, object]]) -> bool:
    """True when any phase recorded a non-completed status."""
    return any(
        info.get("status") in _RESUMABLE_STATUSES
        for info in latest_execution_per_phase.values()
    )


def _build_prompt(
    slash_command: str,
    *,
    run_id: int,
    project_name: str,
    only: list[str] | None,
    exclude: list[str] | None,
    adversarial: bool,
    completed_phases: list[str],
) -> str:
    """Compose the prompt sent to the SDK session."""
    parts: list[str] = []

    if completed_phases:
        phase_list = ", ".join(completed_phases)
        parts.append(
            f"Resume: phases already completed: [{phase_list}]. "
            "Skip those and continue from the next incomplete phase."
        )

    filter_parts: list[str] = []
    if only:
        filter_parts.append(f"only={','.join(only)}")
    if exclude:
        filter_parts.append(f"exclude={','.join(exclude)}")
    filter_parts.append(f"adversarial={'true' if adversarial else 'false'}")
    filters = ", ".join(filter_parts)

    parts.append(
        f"Run {slash_command} with these filters: {filters}. "
        f"Project: {project_name}. Run id: {run_id}."
    )
    return "\n\n".join(parts)


def _run_scan_via_relay(spec: ScanJobSpec, *, compose_path: Path) -> None:
    """Run one scan job through a per-run sandbox relay.

    Separated from the class so tests can monkeypatch it without spawning docker.
    """
    client = SDKRelayClient(compose_path=compose_path)
    try:
        client.start()
        for event in client.submit(spec):
            if isinstance(event, ErrorEvent):
                raise _SDKRuntimeError(
                    f"SDK query error (subtype={event.subtype}): "
                    f"{event.message or 'unknown'}",
                    status_code=event.status_code,
                )
            if isinstance(event, ResultEvent) and event.is_error:
                raise _SDKRuntimeError(
                    f"SDK query error: {event.text or 'unknown'}",
                )
            if isinstance(event, AssistantTextEvent):
                _log.debug("scan sdk: %s", event.text[:200])
    finally:
        client.stop()


def _mint_bearer_token(
    run_id: int,
    *,
    base_path: Path,
) -> str:
    """Mint an MCP bearer token for the scan session."""
    from application.mcp.token_minting import mint_bearer_token

    return mint_bearer_token(f"scan-background-{run_id}", base_path=base_path)


class ScanBackgroundHandle:
    """Opaque handle wrapping the daemon thread's future."""

    def __init__(self, result: Future[str]) -> None:
        self.result = result


class ScanBackgroundLauncher:
    """Runs a non-interactive scan on a daemon thread via the Agent SDK."""

    def __init__(
        self,
        mcp_service: Any,
        availability: BackgroundModeAvailabilityService,
        config: Any,
        scan_phase_repo: ScanPhaseCleanupPort | None = None,
        scan_event_sink: ScanEventSink | None = None,
        scan_run_status_repo: ScanRunStatusPort | None = None,
    ) -> None:
        self._mcp = mcp_service
        self._availability = availability
        self._config = config
        self._scan_phase_repo = scan_phase_repo
        self._scan_event_sink = scan_event_sink
        self._scan_run_status_repo = scan_run_status_repo

    def launch(
        self,
        *,
        run_id: int,
        project_name: str,
        base_path: str,
        interaction_mode: Literal["interactive", "background"],
        billing_method: Literal["plan", "api"] | None,
        only: list[str] | None,
        exclude: list[str] | None,
        adversarial: bool,
        api_key_source: str | None = None,
    ) -> ScanBackgroundHandle:
        if interaction_mode != "background":
            raise ValueError("ScanBackgroundLauncher only handles background mode.")

        availability = self._availability.evaluate()
        resolved_billing: Literal["plan", "api"] = (
            billing_method or self._config.claude.default_billing_method or "plan"
        )

        if resolved_billing == "plan" and not availability.oauth_available:
            raise ValueError(f"plan billing unavailable: {availability.oauth_reason}")
        if resolved_billing == "api" and not availability.api_key_available:
            raise ValueError(f"api billing unavailable: {availability.api_key_reason}")

        repos = load_active_repos(base_path, project_name)
        if not repos:
            raise ScanConfigurationError(
                f"project {project_name!r} has no active repos"
            )
        repo_cwd = repos[0].path
        if not repo_cwd:
            raise ScanConfigurationError(
                f"primary repo for project {project_name!r} has no path configured"
            )

        self._mcp.set_scan_config(
            project=project_name,
            run_id=run_id,
            only=only,
            exclude=exclude,
            adversarial_verification=adversarial,
        )

        # Check phase status for resume preamble.
        # Include the preamble only when a non-completed phase exists
        # (in_progress / failed / rate_limited) so the skill knows to
        # pick up where it left off.
        phase_status = self._mcp.get_scan_phase_status(
            project=project_name,
            run_id=run_id,
        )
        latest = phase_status.get("latest_execution_per_phase", {})
        completed_phases: list[str] = (
            phase_status.get("completed_phases", []) if _needs_resume(latest) else []
        )

        bp = Path(base_path)
        bearer_token = _mint_bearer_token(run_id, base_path=bp)

        # The sandbox cannot reach the host's loopback, so the MCP URL is
        # always addressed through host.docker.internal.
        mcp_server_url = f"http://host.docker.internal:{self._config.mcp.port}/mcp"
        compose_path = bp / COMPOSE_RELATIVE_PATH

        prompt = _build_prompt(
            "/tally-scan-external",
            run_id=run_id,
            project_name=project_name,
            only=only,
            exclude=exclude,
            adversarial=adversarial,
            completed_phases=completed_phases,
        )

        spec = ScanJobSpec(
            model=self._config.claude.model,
            user_prompt=prompt,
            allowed_tools=list(_SCAN_ALLOWED_TOOLS),
            cwd=repo_cwd,
            timeout_seconds=_SDK_TIMEOUT_SECONDS,
            mcp_servers={
                "tally": {
                    "type": "http",
                    "url": mcp_server_url,
                    "headers": {"Authorization": f"Bearer {bearer_token}"},
                }
            },
        )

        fut: Future[str] = Future()
        scan_event_sink = self._scan_event_sink

        def _worker() -> None:
            try:
                _run_scan_via_relay(spec, compose_path=compose_path)
                fut.set_result("done")
            except Exception as exc:
                kind = classify(exc, billing_method=resolved_billing)
                _log.warning(
                    "scan SDK session failed (run_id=%d, error_class=%s): %s",
                    run_id,
                    kind.name,
                    exc,
                )
                if self._scan_phase_repo:
                    self._scan_phase_repo.mark_in_progress_failed(
                        run_id=run_id, error_class=kind.name
                    )
                if self._scan_run_status_repo is not None:
                    terminal_status = (
                        "rate_limited"
                        if kind.name in ("RATE_LIMIT_PLAN", "RATE_LIMIT_API")
                        else "failed"
                    )
                    try:
                        # Compare-and-set: don't trample a user cancel that
                        # arrived while the SDK was dying. Any status outside
                        # the active set means the user or another writer
                        # already decided this run's fate.
                        self._scan_run_status_repo.set_status_if_in(
                            run_id,
                            terminal_status,
                            allowed_current=("queued", "running"),
                        )
                    except Exception as status_exc:
                        _log.warning(
                            "scan status update failed (run_id=%d): %s",
                            run_id,
                            status_exc,
                        )
                if scan_event_sink is not None and kind.name in (
                    "RATE_LIMIT_PLAN",
                    "RATE_LIMIT_API",
                ):
                    try:
                        from domain.pipeline.scan_events import RunRateLimited

                        scan_event_sink.emit(
                            RunRateLimited(
                                run_id=run_id,
                                project_id=None,
                                usage_pool=resolved_billing,
                                message=f"usage pool {resolved_billing} exhausted",
                            )
                        )
                    except Exception:
                        _log.debug("scan event sink emit failed", exc_info=True)
                # set_result instead of set_exception: the consumer inspects
                # state via scan_phase_executions, not by re-raising.
                fut.set_result("terminated")

        Thread(target=_worker, daemon=True).start()
        return ScanBackgroundHandle(result=fut)
