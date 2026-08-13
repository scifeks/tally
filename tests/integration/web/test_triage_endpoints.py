"""Integration tests for triage endpoints."""

from __future__ import annotations

import json
from typing import Any

import pytest

from application.locking import get_registry
from application.triage.run_registry import get_triage_run_registry
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository

pytestmark = pytest.mark.integration


# Fixtures / helpers


@pytest.fixture(autouse=True)
def _reset_triage_state():
    """Reset process-singleton triage state between tests."""
    get_triage_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("triage") is not None:  # type: ignore[attr-defined]
        reg._jobs["triage"] = None  # type: ignore[attr-defined,index]
    yield
    get_triage_run_registry().reset()
    if reg._jobs.get("triage") is not None:  # type: ignore[attr-defined]
        reg._jobs["triage"] = None  # type: ignore[attr-defined,index]


def _seed_scan_run(factory, *, project_id: int) -> int:
    """Insert a scan_runs row and return its id."""
    repo = RunRepository(factory)
    return repo.create(
        project_id=project_id,
        repo_ids=["test-repo"],
        tool_ids=[],
        domains=["code"],
        skip_enrichment=False,
        status="done",
    )


def _seed_triage_batch(
    factory,
    *,
    run_id: int,
    finding_ids: list[int],
    status: str = "pending",
    segment: str = "sast",
    started_at: str | None = None,
    completed_at: str | None = None,
) -> int:
    """Insert a triage_batches row directly (batch_data carries segment)."""
    batch_data: list[dict[str, Any]] = [
        {"id": fid, "tool": "semgrep", "segment": segment} for fid in finding_ids
    ]
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts,"
            "  started_at, completed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                json.dumps(finding_ids),
                json.dumps(batch_data),
                status,
                0,
                started_at,
                completed_at,
            ),
        )
        return cur.lastrowid


# GET /triage  (history)


@pytest.mark.asyncio
async def test_history_empty_returns_200(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/triage")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_history_lists_run_ids_with_triage_batches(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_a = _seed_scan_run(factory, project_id=project_id)
    run_b = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_a, finding_ids=[1], status="completed")
    _seed_triage_batch(factory, run_id=run_b, finding_ids=[2, 3], status="pending")

    resp = await client.get(f"/api/v1/projects/{project_id}/triage")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    ids = {item["scan_run_id"] for item in body["items"]}
    assert ids == {run_a, run_b}


@pytest.mark.asyncio
async def test_history_pagination(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    for _ in range(3):
        rid = _seed_scan_run(factory, project_id=project_id)
        _seed_triage_batch(factory, run_id=rid, finding_ids=[rid], status="pending")

    resp = await client.get(
        f"/api/v1/projects/{project_id}/triage",
        params={"offset": 1, "limit": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["offset"] == 1
    assert body["limit"] == 1


# GET /triage/{scan_run_id}  (detail)


@pytest.mark.asyncio
async def test_detail_returns_batches(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(
        factory,
        run_id=run_id,
        finding_ids=[10, 11],
        status="completed",
        segment="sast",
        started_at="2026-04-25T00:00:00Z",
        completed_at="2026-04-25T00:01:00Z",
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/{run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scan_run_id"] == run_id
    assert body["status"] == "done"
    assert body["total_findings"] == 2
    assert body["processed_findings"] == 2
    assert len(body["batches"]) == 1
    batch = body["batches"][0]
    assert batch["scan_run_id"] == run_id
    assert batch["segment"] == "sast"
    assert batch["finding_ids"] == [10, 11]


@pytest.mark.asyncio
async def test_detail_404_when_no_triage_batches(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    resp = await client.get(f"/api/v1/projects/{project_id}/triage/{run_id}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_detail_returns_queued_when_handle_registered(app_client) -> None:
    from application.locking.cancellation import CancellationToken

    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    get_triage_run_registry().register(
        scan_run_id=run_id,
        project_id=project_id,
        cancel_token=CancellationToken(),
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/{run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scan_run_id"] == run_id
    assert body["project_id"] == project_id
    assert body["status"] == "queued"
    assert body["batches"] == []
    assert body["total_findings"] == 0
    assert body["processed_findings"] == 0


@pytest.mark.asyncio
async def test_detail_404_when_handle_belongs_to_other_project(
    app_client,
) -> None:
    from application.locking.cancellation import CancellationToken

    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    other_project_id = project_id + 9999
    get_triage_run_registry().register(
        scan_run_id=run_id,
        project_id=other_project_id,
        cancel_token=CancellationToken(),
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/{run_id}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_detail_includes_cancelled_batches(app_client) -> None:
    # After cancel_remaining flips pending/in_progress rows to the
    # ``cancelled`` status, the detail response must still surface them
    # so the UI can render them instead of silently dropping (TAL-237).
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(
        factory,
        run_id=run_id,
        finding_ids=[1],
        status="completed",
        completed_at="2026-04-25T00:01:00Z",
        started_at="2026-04-25T00:00:00Z",
    )
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[2], status="pending")
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[3], status="in_progress")

    TriageBatchRepository(factory).cancel_remaining(run_id)

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/{run_id}")
    assert resp.status_code == 200, resp.text
    statuses = sorted(b["status"] for b in resp.json()["batches"])
    assert statuses == ["cancelled", "cancelled", "completed"]


# GET /triage/events (SSE)


@pytest.mark.asyncio
async def test_sse_events_rejects_missing_scan_run_id(app_client) -> None:
    # Defense in depth: the SSE stream must never fan out project-wide
    # events. Callers must scope the subscription to one run (TAL-238).
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/triage/events")
    assert resp.status_code == 422, resp.text


# POST /triage  (dispatch)


@pytest.mark.asyncio
async def test_start_triage_requires_acknowledgement(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_scan_run(factory, project_id=project_id)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={},
        headers=mut_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_start_triage_rejects_false_acknowledgement(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_scan_run(factory, project_id=project_id)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={"acknowledge_injection_risk": False},
        headers=mut_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_start_triage_404_when_no_scan_runs(app_client, monkeypatch) -> None:
    """If the project has no scan_runs, return 404; nothing to triage."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client

    # Wipe any pre-existing scan_runs so latest_run_id() returns None.
    with factory.connect() as conn:
        conn.execute("DELETE FROM scan_runs")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_start_triage_returns_202_and_acquires_slot(
    app_client, monkeypatch
) -> None:
    from application.triage.triage_service import TriageService

    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_scan_run(factory, project_id=project_id)

    # Stub the worker so the spawned thread is a no-op and the lock
    # remains acquired (the route's response is what we are asserting).
    started: dict = {}

    def fake_run_worker(self, **kwargs):
        started.update(kwargs)

    monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["scan_run_id"] == started["scan_run_id"]
    assert body["project_id"] == project_id
    assert body["status"] in {"queued", "running", "done", "failed", "cancelled"}


@pytest.mark.asyncio
async def test_start_triage_runs_worker_end_to_end(app_client, monkeypatch) -> None:
    """Run the real worker with the orchestrator stubbed.

    Why: the previous architecture acquired the ``triage`` job lock in
    the route AND again inside ``TriageRunner.run``. The second acquire
    raised ``JobBusy`` against the slot the route already held, so any
    real production triage failed. The earlier tests stubbed the worker
    entirely, so the bug never surfaced. This test exercises the worker
    end-to-end (orchestrator stubbed), verifying the lock is acquired
    exactly once and released cleanly.
    """
    import threading

    from application.triage import triage_service

    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_scan_run(factory, project_id=project_id)

    captured: dict[str, Any] = {}
    done = threading.Event()

    def fake_run_triage(project, **kwargs):
        captured["project"] = project
        captured["holder_token"] = kwargs.get("holder_token")
        captured["scan_run_id"] = kwargs.get("scan_run_id")
        captured["lock_held_during_call"] = (
            get_registry()._jobs.get("triage")  # type: ignore[attr-defined]
            == kwargs.get("holder_token")
        )
        done.set()
        return {"sessions_run": 0, "success": 0, "failed": 0, "incomplete": 0}

    monkeypatch.setattr(triage_service, "run_triage_for_project", fake_run_triage)

    from application.triage import container as _ctr

    monkeypatch.setattr(_ctr, "ensure_triage_image", lambda *a, **kw: None)
    monkeypatch.setattr(_ctr, "ensure_triage_containers", lambda *a, **kw: None)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text

    assert done.wait(timeout=5.0), "worker did not invoke the orchestrator"

    # The orchestrator was called exactly once, while the lock was held
    # under the holder_token the service minted. No JobBusy was raised.
    assert captured["holder_token"] is not None
    assert captured["lock_held_during_call"] is True

    # Wait for the worker thread to release the lock.
    for _ in range(50):
        if get_registry()._jobs.get("triage") is None:  # type: ignore[attr-defined]
            break
        threading.Event().wait(0.05)
    assert get_registry()._jobs.get("triage") is None, (  # type: ignore[attr-defined]
        "lock not released by the worker"
    )


@pytest.mark.asyncio
async def test_start_triage_409_when_busy(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_scan_run(factory, project_id=project_id)

    # Pre-acquire the triage slot so the next dispatch gets 409.
    get_registry().acquire_job("triage", "test-other-holder")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "JOB_ALREADY_RUNNING"

    # Release for downstream tests (autouse fixture also handles).
    get_registry().release_job("triage", "test-other-holder")


# POST /triage/{scan_run_id}/cancel


@pytest.mark.asyncio
async def test_cancel_404_when_no_run_recorded(app_client, mut_headers=None) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/9999/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_cancel_409_when_already_finished(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="completed")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_cancel_active_returns_202_and_sets_token(app_client) -> None:
    from application.locking.cancellation import CancellationToken

    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)

    token = CancellationToken()
    get_triage_run_registry().register(
        scan_run_id=run_id,
        project_id=project_id,
        cancel_token=token,
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["scan_run_id"] == run_id
    assert body["status"] == "cancelling"
    assert token.is_set()


# Lifespan / event-bus


@pytest.mark.asyncio
async def test_event_bus_has_triage_job_registered(app_client) -> None:
    """The triage stream job must exist so SSE can subscribe to it."""
    client, *_ = app_client
    bus = client._transport.app.state.event_bus  # type: ignore[attr-defined]
    sub_id, _ = await bus.subscribe("triage")
    assert sub_id is not None
    await bus.unsubscribe("triage", sub_id)


# Repository helpers (fast unit-style smoke through the integration DB)


def test_summarize_for_run_empty_returns_none(app_client_sync) -> None:
    factory = app_client_sync
    repo = TriageBatchRepository(factory)
    assert repo.summarize_for_run(99999) is None


@pytest.fixture()
def app_client_sync(tmp_path):
    """Lightweight per-test factory for repository smoke tests."""
    from infrastructure.store.connection import ConnectionFactory

    db = tmp_path / "findings.db"
    factory = ConnectionFactory(db)
    factory.init_schema()
    return factory


def test_summarize_for_run_status_progression(app_client_sync) -> None:
    factory = app_client_sync
    repo = TriageBatchRepository(factory)

    # Seed two batches with different statuses.
    _seed_triage_batch(
        factory,
        run_id=5,
        finding_ids=[1, 2],
        status="completed",
        completed_at="2026-04-25T00:01:00Z",
        started_at="2026-04-25T00:00:00Z",
    )
    _seed_triage_batch(
        factory,
        run_id=5,
        finding_ids=[3],
        status="pending",
    )

    summary = repo.summarize_for_run(5)
    assert summary is not None
    assert summary.status == "running"  # pending present so status = running
    assert summary.total_findings == 3
    assert summary.processed_findings == 2  # only completed batch counts


def test_cancel_remaining_marks_in_flight(app_client_sync) -> None:
    factory = app_client_sync
    repo = TriageBatchRepository(factory)

    _seed_triage_batch(factory, run_id=7, finding_ids=[1], status="pending")
    _seed_triage_batch(factory, run_id=7, finding_ids=[2], status="in_progress")
    _seed_triage_batch(factory, run_id=7, finding_ids=[3], status="completed")

    n = repo.cancel_remaining(7)
    assert n == 2

    summary = repo.summarize_for_run(7)
    assert summary is not None
    assert summary.status == "cancelled"
    assert summary.counts_by_status["cancelled"] == 2
    assert summary.counts_by_status["completed"] == 1


@pytest.mark.asyncio
async def test_active_returns_null_when_none(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/triage/active")
    assert resp.status_code == 200, resp.text
    assert resp.json() is None


@pytest.mark.asyncio
async def test_active_returns_summary_when_handle_registered(app_client) -> None:
    from application.locking.cancellation import CancellationToken

    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(
        factory,
        run_id=run_id,
        finding_ids=[1, 2],
        status="in_progress",
    )
    get_triage_run_registry().register(
        scan_run_id=run_id,
        project_id=project_id,
        cancel_token=CancellationToken(),
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/active")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None
    assert body["scan_run_id"] == run_id
    assert body["project_id"] == project_id
    assert body["status"] == "running"


@pytest.mark.asyncio
async def test_active_returns_queued_placeholder_when_no_batches(app_client) -> None:
    """Race window: registered handle but batches not yet written."""
    from application.locking.cancellation import CancellationToken

    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    get_triage_run_registry().register(
        scan_run_id=run_id,
        project_id=project_id,
        cancel_token=CancellationToken(),
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/active")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None
    assert body["status"] == "queued"
    assert body["scan_run_id"] == run_id


@pytest.mark.asyncio
async def test_active_filters_other_projects(app_client) -> None:
    """A handle registered for a different project must not surface here."""
    from application.locking.cancellation import CancellationToken

    client, *_, project_id = app_client
    other_project_id = project_id + 9999
    get_triage_run_registry().register(
        scan_run_id=4242,
        project_id=other_project_id,
        cancel_token=CancellationToken(),
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/active")
    assert resp.status_code == 200, resp.text
    assert resp.json() is None


@pytest.mark.asyncio
async def test_latest_404_when_no_history(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/triage/latest")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_latest_returns_newest_run(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    older = _seed_scan_run(factory, project_id=project_id)
    newer = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=older, finding_ids=[1], status="completed")
    _seed_triage_batch(factory, run_id=newer, finding_ids=[2, 3], status="pending")

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/latest")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scan_run_id"] == newer
    assert body["project_id"] == project_id
    assert body["status"] == "running"
    assert body["total_findings"] == 2


@pytest.mark.asyncio
async def test_latest_404_when_newer_scan_exists(app_client) -> None:
    """A newer scan_run makes the latest triage stale."""
    client, _fid, _rag, factory, _muth, project_id = app_client
    old_run = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(
        factory,
        run_id=old_run,
        finding_ids=[1],
        status="completed",
    )
    _seed_scan_run(factory, project_id=project_id)

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/latest")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_latest_404_when_terminal(app_client) -> None:
    """A completed triage on the latest scan is terminal; returns 404."""
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(
        factory,
        run_id=run_id,
        finding_ids=[1],
        status="completed",
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/latest")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_latest_200_when_still_running(app_client) -> None:
    """A non-terminal triage on the latest scan returns 200."""
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(
        factory,
        run_id=run_id,
        finding_ids=[1],
        status="pending",
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/latest")
    assert resp.status_code == 200, resp.text
    assert resp.json()["scan_run_id"] == run_id
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_resume_404_when_no_triage_history(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_resume_422_when_acknowledgement_missing(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
        json={},
        headers=mut_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_resume_409_when_terminal(app_client) -> None:
    """A run whose batches are all completed is not resumable."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="completed")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TRIAGE_NOT_RESUMABLE"


@pytest.mark.asyncio
async def test_resume_409_when_cancelled(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="cancelled")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TRIAGE_NOT_RESUMABLE"


@pytest.mark.asyncio
async def test_resume_409_when_lock_held(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

    get_registry().acquire_job("triage", "test-other-holder")
    try:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
            json={"acknowledge_injection_risk": True},
            headers=mut_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "JOB_ALREADY_RUNNING"
    finally:
        get_registry().release_job("triage", "test-other-holder")


@pytest.mark.asyncio
async def test_resume_202_dispatches_with_explicit_scan_run_id(
    app_client, monkeypatch
) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1], status="failed")

    from application.triage.triage_service import TriageService

    started: dict = {}

    def fake_run_worker(self, **kwargs):
        started.update(kwargs)

    monkeypatch.setattr(TriageService, "_run_worker", fake_run_worker)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage/{run_id}/resume",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["scan_run_id"] == run_id
    assert body["project_id"] == project_id
    # Critical: the resume path must pin the scan_run_id and set is_resume.
    assert started["scan_run_id"] == run_id
    assert started["is_resume"] is True


# Repository: reset_for_resume


def test_reset_for_resume_flips_in_progress_and_failed(app_client_sync) -> None:
    factory = app_client_sync
    repo = TriageBatchRepository(factory)
    _seed_triage_batch(factory, run_id=11, finding_ids=[1], status="in_progress")
    _seed_triage_batch(factory, run_id=11, finding_ids=[2], status="failed")
    _seed_triage_batch(factory, run_id=11, finding_ids=[3], status="completed")

    n = repo.reset_for_resume(11)
    assert n == 2

    rows = repo.list_for_run(11)
    statuses = sorted(r.status for r in rows)
    assert statuses == ["completed", "pending", "pending"]


def test_reset_for_resume_resets_failed_regardless_of_attempts(
    app_client_sync,
) -> None:
    """Failed batches are always eligible for manual resume."""
    factory = app_client_sync
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts)"
            " VALUES (?, ?, ?, ?, ?)",
            (12, json.dumps([1]), json.dumps([{"id": 1}]), "failed", 5),
        )
    repo = TriageBatchRepository(factory)
    n = repo.reset_for_resume(12)
    assert n == 1

    rows = repo.list_for_run(12)
    assert rows[0].status == "pending"


# GET /triage/{scan_run_id} with after_batch_id filter


@pytest.mark.asyncio
async def test_detail_filters_by_after_batch_id(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    first_id = _seed_triage_batch(factory, run_id=run_id, finding_ids=[1])
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[2])
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[3])

    resp = await client.get(
        f"/api/v1/projects/{project_id}/triage/{run_id}",
        params={"after_batch_id": first_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = sorted(b["id"] for b in body["batches"])
    assert ids == [first_id + 1, first_id + 2]
    assert body["total_findings"] == 2


@pytest.mark.asyncio
async def test_detail_after_batch_id_absent_returns_all(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1])
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[2])

    resp = await client.get(f"/api/v1/projects/{project_id}/triage/{run_id}")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["batches"]) == 2


# GET /triage/{scan_run_id}/max-batch-id


@pytest.mark.asyncio
async def test_max_batch_id_route_returns_null_when_empty(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    resp = await client.get(
        f"/api/v1/projects/{project_id}/triage/{run_id}/max-batch-id"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"max_batch_id": None}


@pytest.mark.asyncio
async def test_max_batch_id_route_returns_max(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    _seed_triage_batch(factory, run_id=run_id, finding_ids=[1])
    latest = _seed_triage_batch(factory, run_id=run_id, finding_ids=[2])
    resp = await client.get(
        f"/api/v1/projects/{project_id}/triage/{run_id}/max-batch-id"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"max_batch_id": latest}


# POST /triage with previous_max_batch_id


@pytest.mark.asyncio
async def test_start_response_includes_previous_max_batch_id(
    app_client, monkeypatch
) -> None:
    from application.triage.triage_service import TriageService

    client, _fid, _rag, factory, mut_headers, project_id = app_client
    run_id = _seed_scan_run(factory, project_id=project_id)
    prior = _seed_triage_batch(factory, run_id=run_id, finding_ids=[1])

    def _noop(self, **kwargs):
        return None

    monkeypatch.setattr(TriageService, "_run_worker", _noop)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/triage",
        json={"acknowledge_injection_risk": True},
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["previous_max_batch_id"] == prior
