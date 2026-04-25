"""Integration tests for the Phase 6 triage endpoints."""

from __future__ import annotations

import json
from typing import Any

import pytest

from application.locking import get_registry
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository
from web.adapters.triage_run_registry import get_triage_run_registry

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


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
    """Insert a Phase 5.1 scan_runs row and return its id."""
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


# ---------------------------------------------------------------------------
# GET /triage  (history)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# GET /triage/{scan_run_id}  (detail)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# POST /triage  (dispatch)
# ---------------------------------------------------------------------------


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
    """If the project has no scan_runs, return 404 — nothing to triage."""
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
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_scan_run(factory, project_id=project_id)

    # Replace the worker so the request returns immediately.
    started: dict = {}

    def fake_start_triage_thread(**kwargs):
        started.update(kwargs)
        # don't release the lock — worker would normally hold then release

    monkeypatch.setattr("web.api.triage.start_triage_thread", fake_start_triage_thread)

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


# ---------------------------------------------------------------------------
# POST /triage/{scan_run_id}/cancel
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Lifespan / event-bus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_has_triage_job_registered(app_client) -> None:
    """The triage stream job must exist so SSE can subscribe to it."""
    client, *_ = app_client
    bus = client._transport.app.state.event_bus  # type: ignore[attr-defined]
    sub_id, _ = await bus.subscribe("triage")
    assert sub_id is not None
    await bus.unsubscribe("triage", sub_id)


# ---------------------------------------------------------------------------
# Repository helpers (fast unit-style smoke through the integration DB)
# ---------------------------------------------------------------------------


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
    assert summary.status == "running"  # pending present → running
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
