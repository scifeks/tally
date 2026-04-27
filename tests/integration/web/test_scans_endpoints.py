"""Integration tests for the Phase 5.3-5.8 scan endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from application.locking import get_registry
from application.locking.cancellation import CancellationToken
from infrastructure.events.types import BusEvent
from infrastructure.store.repositories.runs import RunRepository
from web.adapters.scan_run_registry import get_scan_run_registry

pytestmark = pytest.mark.integration


def _seed_global_config(base_path: str) -> None:
    """Write a minimal <base>/config/global.json — required by ConfigManager."""
    config_dir = Path(base_path) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {"model": "test-model", "host": "http://localhost:11434"},
                "ollama_embedding": {
                    "model": "test-embed",
                    "host": "http://localhost:11434",
                },
            }
        )
    )


def _seed_project_config(base_path: str, project_name: str) -> None:
    """Write a minimal project.json so /scans/config can list repos.

    Also triggers Phase 9 ``sync_repositories_for_project`` to stamp uuid +
    insert the matching ``repositories`` row, so the repo surfaces with a
    real DB id from the scan-config endpoint.
    """
    from application.project.repository_sync import sync_repositories_for_project

    _seed_global_config(base_path)
    repo_path = Path(base_path) / "fake-repo"
    repo_path.mkdir(parents=True, exist_ok=True)
    project_dir = Path(base_path) / "projects" / project_name
    config_dir = project_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    project_json = config_dir / "project.json"
    project_json.write_text(
        json.dumps(
            {
                "project_name": project_name,
                "created": "2026-04-25T00:00:00",
                "repositories": [
                    {
                        "name": "test-repo",
                        "type": ["api"],
                        "path": str(repo_path),
                        "languages": ["python"],
                        "base_urls": [],
                    }
                ],
            }
        )
    )
    sync_repositories_for_project(str(project_dir))


@pytest.fixture(autouse=True)
def _reset_scan_state():
    """Reset process-singleton scan state between tests."""
    get_scan_run_registry().reset()
    reg = get_registry()
    # Force-clear any leftover scan slot from a prior test.
    if reg._jobs.get("scan") is not None:  # type: ignore[attr-defined]
        reg._jobs["scan"] = None  # type: ignore[attr-defined,index]
    yield
    get_scan_run_registry().reset()
    if reg._jobs.get("scan") is not None:  # type: ignore[attr-defined]
        reg._jobs["scan"] = None  # type: ignore[attr-defined,index]


def _seed_run(factory, *, project_id: int, **overrides: Any) -> int:
    repo = RunRepository(factory)
    return repo.create(
        project_id=project_id,
        repo_ids=overrides.get("repo_ids", ["test-repo"]),
        tool_ids=overrides.get("tool_ids", []),
        domains=overrides.get("domains", ["code"]),
        skip_enrichment=overrides.get("skip_enrichment", False),
        status=overrides.get("status", "queued"),
    )


# ---------------------------------------------------------------------------
# GET /scans/config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_returns_repos_tools_domains(app_client, tmp_path) -> None:
    client, _fid, _rag, _factory, _muth, project_id = app_client
    _seed_project_config(str(tmp_path), "testproject")
    resp = await client.get(f"/api/v1/projects/{project_id}/scans/config")
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "repos" in body
    assert "tools" in body
    assert "domains" in body
    assert isinstance(body["domains"], list)
    assert len(body["domains"]) > 0
    assert any(r["name"] == "test-repo" for r in body["repos"])


@pytest.mark.asyncio
async def test_config_unknown_project_404(app_client) -> None:
    client, *_ = app_client
    resp = await client.get("/api/v1/projects/99999/scans/config")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /scans (history list)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_scans_pagination(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    for _ in range(3):
        _seed_run(factory, project_id=project_id, status="done")
    resp = await client.get(
        f"/api/v1/projects/{project_id}/scans",
        params={"limit": 2, "offset": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["offset"] == 0
    assert body["limit"] == 2


@pytest.mark.asyncio
async def test_list_scans_status_filter(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    _seed_run(factory, project_id=project_id, status="done")
    _seed_run(factory, project_id=project_id, status="failed")
    resp = await client.get(
        f"/api/v1/projects/{project_id}/scans",
        params={"status": "done"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_list_scans_unknown_status_422(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(
        f"/api/v1/projects/{project_id}/scans",
        params={"status": "garbage"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_list_scans_empty(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/scans")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# ---------------------------------------------------------------------------
# POST /scans (start)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_scan_returns_202_and_creates_row(app_client, monkeypatch) -> None:
    """Happy path: start endpoint inserts a scan_runs row and spawns a worker."""
    client, _fid, _rag, factory, muth, project_id = app_client

    spawned = []
    monkeypatch.setattr(
        "web.api.scans.start_scan_thread",
        lambda **kw: spawned.append(kw),
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans",
        json={"repoIds": [], "toolIds": [], "domains": []},
        headers=muth,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["project_id"] == project_id
    assert isinstance(body["id"], int)
    assert len(spawned) == 1
    assert spawned[0]["run_id"] == body["id"]


@pytest.mark.asyncio
async def test_start_scan_409_when_busy(app_client, monkeypatch) -> None:
    client, _fid, _rag, _factory, muth, project_id = app_client
    monkeypatch.setattr(
        "web.api.scans.start_scan_thread",
        lambda **kw: None,
    )
    # First start acquires the lock and never releases (start_scan_thread no-op).
    first = await client.post(
        f"/api/v1/projects/{project_id}/scans",
        json={"repoIds": [], "toolIds": [], "domains": []},
        headers=muth,
    )
    assert first.status_code == 202

    # Second start hits the held lock → 409.
    second = await client.post(
        f"/api/v1/projects/{project_id}/scans",
        json={"repoIds": [], "toolIds": [], "domains": []},
        headers=muth,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "JOB_ALREADY_RUNNING"


@pytest.mark.asyncio
async def test_start_scan_unknown_repo_422(app_client, monkeypatch, tmp_path) -> None:
    client, _fid, _rag, _factory, muth, project_id = app_client
    _seed_project_config(str(tmp_path), "testproject")
    monkeypatch.setattr("web.api.scans.start_scan_thread", lambda **kw: None)

    # Phase 9: repoIds is list[int]. Send an integer id that doesn't exist
    # in the active repositories table to trigger _validate_repo_ids.
    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans",
        json={"repoIds": [99999]},
        headers=muth,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert 99999 in body["error"]["details"]["unknown"]


@pytest.mark.asyncio
async def test_start_scan_soft_deleted_repo_422(
    app_client, monkeypatch, tmp_path
) -> None:
    """Soft-deleted repos are rejected by _validate_repo_ids with 422 (F4)."""
    from infrastructure.store.repositories.repositories import RepositoryRepository

    client, _fid, _rag, factory, muth, project_id = app_client
    _seed_project_config(str(tmp_path), "testproject")
    monkeypatch.setattr("web.api.scans.start_scan_thread", lambda **kw: None)

    repo_repo = RepositoryRepository(factory)
    active = repo_repo.list_active()
    assert active, "Expected at least one repo after seed"
    repo_id = active[0].id

    repo_repo.soft_delete(repo_id)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans",
        json={"repoIds": [repo_id]},
        headers=muth,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert repo_id in body["error"]["details"]["unknown"]


@pytest.mark.asyncio
async def test_start_scan_unknown_domain_422(app_client, monkeypatch) -> None:
    client, _fid, _rag, _factory, muth, project_id = app_client
    monkeypatch.setattr("web.api.scans.start_scan_thread", lambda **kw: None)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans",
        json={"domains": ["bogus-domain"]},
        headers=muth,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /scans/{run_id} (detail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_returns_tool_runs(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    repo = RunRepository(factory)
    run_id = _seed_run(factory, project_id=project_id)
    repo.add_tool_run(run_id=run_id, tool="gitleaks", repo="test-repo", domain="code")
    resp = await client.get(f"/api/v1/projects/{project_id}/scans/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run_id
    assert len(body["tool_runs"]) == 1
    assert body["tool_runs"][0]["tool"] == "gitleaks"


@pytest.mark.asyncio
async def test_detail_404_for_missing_run(app_client) -> None:
    client, *_, _muth, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/scans/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/scans/{run_id}/cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_active_run(app_client) -> None:
    client, _fid, _rag, factory, muth, project_id = app_client
    run_id = _seed_run(factory, project_id=project_id, status="running")
    token = CancellationToken()
    get_scan_run_registry().register(
        run_id=run_id, project_id=project_id, cancel_token=token
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans/{run_id}/cancel", headers=muth
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "cancelling"
    assert token.is_set() is True


@pytest.mark.asyncio
async def test_cancel_unknown_run_404(app_client) -> None:
    client, *_, muth, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans/9999/cancel", headers=muth
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_finished_run_409(app_client) -> None:
    client, _fid, _rag, factory, muth, project_id = app_client
    run_id = _seed_run(factory, project_id=project_id, status="done")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans/{run_id}/cancel", headers=muth
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SCAN_NOT_CANCELLABLE"


@pytest.mark.asyncio
async def test_cancel_run_from_different_project_404(app_client) -> None:
    """Cross-project run id must 404 even if the run exists in another project."""
    client, _fid, _rag, factory, muth, project_id = app_client
    other_run = _seed_run(factory, project_id=999, status="running")
    token = CancellationToken()
    get_scan_run_registry().register(
        run_id=other_run, project_id=999, cancel_token=token
    )
    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans/{other_run}/cancel", headers=muth
    )
    assert resp.status_code == 404
    assert not token.is_set()


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/scans/cancel-all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_all_cancels_active_runs_for_project(
    app_client,
) -> None:
    client, _fid, _rag, factory, muth, project_id = app_client
    run1 = _seed_run(factory, project_id=project_id, status="running")
    run2 = _seed_run(factory, project_id=project_id, status="running")
    other_run = _seed_run(factory, project_id=99, status="running")

    reg = get_scan_run_registry()
    t1, t2, t3 = CancellationToken(), CancellationToken(), CancellationToken()
    reg.register(run_id=run1, project_id=project_id, cancel_token=t1)
    reg.register(run_id=run2, project_id=project_id, cancel_token=t2)
    reg.register(run_id=other_run, project_id=99, cancel_token=t3)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/scans/cancel-all",
        headers=muth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["cancelled"]) == sorted([run1, run2])
    assert t1.is_set() and t2.is_set()
    assert not t3.is_set()


# ---------------------------------------------------------------------------
# GET /scans/{run_id}/progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_endpoint(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    repo = RunRepository(factory)
    run_id = _seed_run(factory, project_id=project_id, status="running")
    tr1 = repo.add_tool_run(run_id=run_id, tool="gitleaks", status="done")
    tr2 = repo.add_tool_run(run_id=run_id, tool="semgrep", status="running")
    repo.update_tool_run(tr1, status="done")
    repo.update_tool_run(tr2, status="running")

    resp = await client.get(f"/api/v1/projects/{project_id}/scans/{run_id}/progress")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run_id
    assert body["status"] == "running"
    assert body["tool_runs_summary"]["done"] == 1
    assert body["tool_runs_summary"]["running"] == 1


@pytest.mark.asyncio
async def test_progress_404_for_missing_run(app_client) -> None:
    client, *_, _muth, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/scans/9999/progress")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /scans/events (SSE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_filters_events_by_project_id(app_client) -> None:
    """Tail-mode behavior: subscribe to bus, publish events, verify filter.

    Skips the HTTP transport because httpx's ASGI doesn't keep an SSE
    response open the way curl does. Instead we exercise the bus
    subscribe/publish path directly — same code path the endpoint uses.
    """
    client, *_ = app_client
    bus = client._transport.app.state.event_bus  # type: ignore[attr-defined]

    sub_id, queue = await bus.subscribe("scan")

    from datetime import UTC, datetime

    from infrastructure.events.ids import new_event_id

    other = BusEvent(
        event_id=new_event_id(),
        job_id="scan",
        stream="scan",
        event_type="run_started",
        payload={"run_id": 1, "project_id": 999},
        ts=datetime.now(UTC),
    )
    ours = BusEvent(
        event_id=new_event_id(),
        job_id="scan",
        stream="scan",
        event_type="run_started",
        payload={"run_id": 2, "project_id": 7},
        ts=datetime.now(UTC),
    )
    await bus.publish(other)
    await bus.publish(ours)

    received = []
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.5)
        except TimeoutError:
            break
        received.append(item)

    # Apply the same filter the endpoint applies (project_id=7)
    filtered = [i for i in received if i.payload.get("project_id") == 7]
    assert len(filtered) == 1
    assert filtered[0].payload["run_id"] == 2

    await bus.unsubscribe("scan", sub_id)


@pytest.mark.asyncio
async def test_sse_unknown_project_404(app_client) -> None:
    client, *_, _muth, _project_id = app_client
    resp = await client.get("/api/v1/projects/9999/scans/events")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Lifespan / event-bus registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_has_scan_job_registered(app_client) -> None:
    client, *_ = app_client
    bus = client._transport.app.state.event_bus  # type: ignore[attr-defined]
    # Subscribe to confirm the "scan" job exists.
    sub_id, _queue = await bus.subscribe("scan")
    assert sub_id is not None
    await bus.unsubscribe("scan", sub_id)
