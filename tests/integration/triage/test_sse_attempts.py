"""Integration test for BatchAttempt* SSE events.

Verifies the triage runner emits attempt-level events (started, completed,
failed, rate_limited) so the web UI can show per-attempt progress.
Covers the happy path, plan-to-api failover sequence, rate-limit abort
without failover, and resume with correct attempt numbering.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.triage_agent import (  # noqa: E402
    PreparedTriageSession,
    TriageBackendUnavailable,
)
from application.triage.factory import ResolvedTriageConfig  # noqa: E402
from application.triage.prompts.triage_prompt import TriagePrompt  # noqa: E402
from application.triage.runner import TriageRunner  # noqa: E402
from application.triage.verdict import Verdict  # noqa: E402
from infrastructure.anthropic.error_classifier import ErrorClass  # noqa: E402
from infrastructure.events.bus import EventBus  # noqa: E402
from infrastructure.events.types import BusEvent  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.audit import AuditRepository  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import (  # noqa: E402
    TriageBatchRepository,
)
from tests.finding_helpers import normalize_test_findings  # noqa: E402
from web.adapters.event_bus_triage_sink import EventBusTriageSink  # noqa: E402

pytestmark = pytest.mark.integration

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "repo": "testrepo",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "potential",
    "file_path": "src/app.py",
    "rule_id": "python.sqli",
    "description": "SQL injection",
}


async def _collect_events_until(
    queue: asyncio.Queue,
    *,
    event_type: str,
    timeout: float = 10.0,
) -> list[BusEvent]:
    """Collect events until *event_type* is seen or timeout."""
    events: list[BusEvent] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            event = await asyncio.wait_for(queue.get(), timeout=remaining)
            if not isinstance(event, BusEvent):
                continue
            events.append(event)
            if event.event_type == event_type:
                break
        except TimeoutError:
            break
    return events


def _make_verdict(finding_id: int) -> Verdict:
    return Verdict(
        finding_id=finding_id,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="high",
        reasoning="test reasoning",
        remediation="fix it",
        attack_vector="network",
        access_required="none",
        exploitation_complexity="low",
        user_interaction="none",
        call_stack=[],
    )


class _StubTriageBackend:
    """Returns a canned Verdict for each finding."""

    @contextmanager
    def prepare_session(self, *, project: str, run_id: int, app_root: Path):
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(
        self,
        prompt: TriagePrompt,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        return _make_verdict(finding_id)


class _RateLimitingBackend:
    """Raises TriageBackendUnavailable on every call."""

    def __init__(self, error_class: ErrorClass):
        self._error_class = error_class

    @contextmanager
    def prepare_session(self, *, project: str, run_id: int, app_root: Path):
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(
        self,
        prompt: TriagePrompt,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        raise TriageBackendUnavailable("rate limited", error_class=self._error_class)


def _seed_project(
    tmp_path: Path,
    *,
    finding_count: int = 1,
) -> tuple[
    str,
    int,
    RunRepository,
    FindingRepository,
    TriageBatchRepository,
    AuditRepository,
    ConnectionFactory,
]:
    """Seed a project with findings and return all the repos + factory."""
    project = "test"
    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_path, project)
    factory = ConnectionFactory(
        tmp_path / "projects" / project / "sqlite" / "findings.db"
    )
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, path) VALUES (?, ?)",
            ("testrepo", "/tmp/fakerepo"),
        )
        repo_id = cur.lastrowid

    run_id = run_repo.create_run({})
    batch = [
        {**_BASE_FINDING, "repo_id": repo_id, "file_path": f"src/file{i}.py"}
        for i in range(finding_count)
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(batch))
    return (
        project,
        run_id,
        run_repo,
        finding_repo,
        triage_repo,
        audit_repo,
        factory,
    )


def _make_tool_registry() -> MagicMock:
    mock_semgrep = MagicMock()
    mock_semgrep.name = "semgrep"
    mock_semgrep.skip = False
    mock_semgrep.scan_segment = "sast"
    registry = MagicMock()
    registry.get_all_tools.return_value = []
    registry.get_tool.return_value = mock_semgrep
    return registry


async def _wire_event_bus() -> tuple[
    EventBus, EventBusTriageSink, Any, asyncio.Queue[Any]
]:
    """Create an EventBus wired to an AsyncPublisher."""
    from application.ports.event_publisher import EventPublisherPort

    event_bus = EventBus()
    await event_bus.register_job("triage", "triage")
    sub_id, queue = await event_bus.subscribe("triage")

    class AsyncPublisher:
        def __init__(self, bus: EventBus, loop: asyncio.AbstractEventLoop):
            self._bus = bus
            self._loop = loop

        def publish_threadsafe(self, event: BusEvent) -> None:
            asyncio.run_coroutine_threadsafe(self._bus.publish(event), self._loop)

    loop = asyncio.get_event_loop()
    publisher = cast(EventPublisherPort, AsyncPublisher(event_bus, loop))
    sink = EventBusTriageSink(publisher)
    return event_bus, sink, sub_id, queue


async def test_sse_emits_attempt_events(tmp_path: Path):
    """BatchAttemptStarted and BatchAttemptCompleted events are emitted."""
    project, run_id, run_repo, finding_repo, triage_repo, audit_repo, _ = _seed_project(
        tmp_path, finding_count=3
    )
    event_bus, sink, sub_id, queue = await _wire_event_bus()

    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        tmp_path,
        event_sink=sink,
        scan_run_id=run_id,
        triage_backend=_StubTriageBackend(),
        session_timeout_seconds=60,
        tool_registry=_make_tool_registry(),
        finding_repo=finding_repo,
        repo_paths={"testrepo": Path("/tmp/fakerepo")},
        triage_provider="test",
        billing_method="plan",
    )

    task = asyncio.create_task(asyncio.to_thread(runner.run))
    events = await _collect_events_until(queue, event_type="run_completed")
    await task
    await event_bus.unsubscribe("triage", sub_id)

    event_types = [e.event_type for e in events]
    assert "run_started" in event_types
    assert "batch_attempt_started" in event_types
    assert "batch_attempt_completed" in event_types

    attempt_started = next(e for e in events if e.event_type == "batch_attempt_started")
    assert attempt_started.payload["batch_id"] > 0
    assert attempt_started.payload["attempt_number"] == 1
    assert attempt_started.payload["usage_pool"] == "plan"

    attempt_completed = next(
        e for e in events if e.event_type == "batch_attempt_completed"
    )
    assert attempt_completed.payload["batch_id"] > 0
    assert attempt_completed.payload["attempt_number"] == 1
    assert attempt_completed.payload["usage_pool"] == "plan"


async def test_failover_emits_rate_limited_then_started_then_completed(
    tmp_path: Path,
):
    """Plan-to-api failover emits the full attempt event sequence:
    Started(1,plan) -> RateLimited(1,plan) -> Started(2,api) -> Completed(2,api).
    """
    project, run_id, run_repo, finding_repo, triage_repo, audit_repo, _ = _seed_project(
        tmp_path, finding_count=1
    )
    event_bus, sink, sub_id, queue = await _wire_event_bus()

    plan_backend = _RateLimitingBackend(ErrorClass.RATE_LIMIT_PLAN)
    api_backend = _StubTriageBackend()

    resolved_config = ResolvedTriageConfig(
        provider_name="claude_sdk",
        base_url="",
        model="test",
        timeout_seconds=30,
        retry_count=0,
        debug=False,
        billing_method="plan",
        api_key_source="sk-test",
        auto_failover=True,
    )

    factory = MagicMock()
    factory.create.return_value = api_backend

    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        tmp_path,
        event_sink=sink,
        scan_run_id=run_id,
        triage_backend=plan_backend,
        session_timeout_seconds=60,
        tool_registry=_make_tool_registry(),
        finding_repo=finding_repo,
        repo_paths={"testrepo": Path("/tmp/fakerepo")},
        triage_provider="test",
        billing_method="plan",
        agent_factory=factory,
        resolved_config=resolved_config,
        enable_auto_failover=True,
        api_key_available=True,
    )

    task = asyncio.create_task(asyncio.to_thread(runner.run))
    events = await _collect_events_until(queue, event_type="run_completed")
    await task
    await event_bus.unsubscribe("triage", sub_id)

    attempt_events = [e for e in events if e.event_type.startswith("batch_attempt_")]
    types_and_data = [
        (
            e.event_type,
            e.payload["attempt_number"],
            e.payload["usage_pool"],
        )
        for e in attempt_events
    ]

    assert types_and_data == [
        ("batch_attempt_started", 1, "plan"),
        ("batch_attempt_rate_limited", 1, "plan"),
        ("batch_attempt_started", 2, "api"),
        ("batch_attempt_completed", 2, "api"),
    ]


async def test_rate_limit_abort_without_failover(tmp_path: Path):
    """When billing_method='api' from the start, a rate limit aborts with
    RunRateLimited and no new attempt is created.
    """
    project, run_id, run_repo, finding_repo, triage_repo, audit_repo, _ = _seed_project(
        tmp_path, finding_count=1
    )
    event_bus, sink, sub_id, queue = await _wire_event_bus()

    backend = _RateLimitingBackend(ErrorClass.RATE_LIMIT_API)

    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        tmp_path,
        event_sink=sink,
        scan_run_id=run_id,
        triage_backend=backend,
        session_timeout_seconds=60,
        tool_registry=_make_tool_registry(),
        finding_repo=finding_repo,
        repo_paths={"testrepo": Path("/tmp/fakerepo")},
        triage_provider="test",
        billing_method="api",
    )

    task = asyncio.create_task(asyncio.to_thread(runner.run))
    events = await _collect_events_until(queue, event_type="run_rate_limited")
    await task
    await event_bus.unsubscribe("triage", sub_id)

    event_types = [e.event_type for e in events]
    assert "run_rate_limited" in event_types
    assert "batch_attempt_started" in event_types
    assert "batch_attempt_rate_limited" in event_types

    rate_limited_event = next(e for e in events if e.event_type == "run_rate_limited")
    assert rate_limited_event.payload["usage_pool"] == "api"

    # Only one attempt was started; no failover attempt
    started_events = [e for e in events if e.event_type == "batch_attempt_started"]
    assert len(started_events) == 1
    assert started_events[0].payload["attempt_number"] == 1


async def test_resume_carries_correct_attempt_number(tmp_path: Path):
    """After a rate_limited run, resume produces attempt_number=2."""
    project, run_id, run_repo, finding_repo, triage_repo, audit_repo, _ = _seed_project(
        tmp_path, finding_count=1
    )
    event_bus, sink, sub_id, queue = await _wire_event_bus()

    # First run: rate-limit on api so it aborts
    abort_backend = _RateLimitingBackend(ErrorClass.RATE_LIMIT_API)
    runner1 = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        tmp_path,
        event_sink=sink,
        scan_run_id=run_id,
        triage_backend=abort_backend,
        session_timeout_seconds=60,
        tool_registry=_make_tool_registry(),
        finding_repo=finding_repo,
        repo_paths={"testrepo": Path("/tmp/fakerepo")},
        triage_provider="test",
        billing_method="api",
    )
    task1 = asyncio.create_task(asyncio.to_thread(runner1.run))
    await _collect_events_until(queue, event_type="run_rate_limited")
    await task1

    # Reset for resume
    triage_repo.reset_for_resume(run_id)

    # Drain leftover events
    while not queue.empty():
        queue.get_nowait()

    # Resume: now succeeds
    runner2 = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        tmp_path,
        event_sink=sink,
        scan_run_id=run_id,
        triage_backend=_StubTriageBackend(),
        session_timeout_seconds=60,
        tool_registry=_make_tool_registry(),
        finding_repo=finding_repo,
        repo_paths={"testrepo": Path("/tmp/fakerepo")},
        triage_provider="test",
        billing_method="api",
    )
    task2 = asyncio.create_task(asyncio.to_thread(runner2.run, skip_batching=True))
    events = await _collect_events_until(queue, event_type="run_completed")
    await task2
    await event_bus.unsubscribe("triage", sub_id)

    started = [e for e in events if e.event_type == "batch_attempt_started"]
    assert len(started) == 1
    assert started[0].payload["attempt_number"] == 2
    assert started[0].payload["usage_pool"] == "api"

    completed = [e for e in events if e.event_type == "batch_attempt_completed"]
    assert len(completed) == 1
    assert completed[0].payload["attempt_number"] == 2
