"""Integration tests for Phase 7.5/7.6 draft endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from application.locking import get_registry
from application.reporting.drafts import SECTION_REGISTRY
from infrastructure.store.repositories.drafts import DraftRepository
from web.adapters.draft_run_registry import get_draft_run_registry

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_draft_state():
    """Reset draft registry and report lock between tests."""
    get_draft_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("report") is not None:  # type: ignore[attr-defined]
        reg._jobs["report"] = None  # type: ignore[attr-defined,index]
    yield
    get_draft_run_registry().reset()
    if reg._jobs.get("report") is not None:  # type: ignore[attr-defined]
        reg._jobs["report"] = None  # type: ignore[attr-defined,index]


def _seed_draft(
    factory,
    *,
    section: str,
    status: str = "draft",
) -> None:
    """Insert a draft row directly via DraftRepository."""
    repo = DraftRepository(factory)
    repo.upsert_generating(section)
    if status == "draft":
        repo.mark_drafted(section)
    elif status == "reviewed":
        repo.mark_reviewed(section, "upload.md")


def _draft_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "testproject" / "reports" / "draft"


@pytest.mark.asyncio
async def test_list_drafts_returns_all_sections_not_generated(
    app_client,
) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/reports/drafts")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == len(SECTION_REGISTRY)
    for item in items:
        assert item["status"] == "not_generated"
        assert item["word_count"] is None
        assert item["preview"] is None


@pytest.mark.asyncio
async def test_list_drafts_reflects_db_row(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    _seed_draft(factory, section="executive-summary", status="draft")
    resp = await client.get(f"/api/v1/projects/{project_id}/reports/drafts")
    assert resp.status_code == 200
    by_section = {i["section"]: i for i in resp.json()}
    assert by_section["executive-summary"]["status"] == "draft"
    for s, item in by_section.items():
        if s != "executive-summary":
            assert item["status"] == "not_generated"


@pytest.mark.asyncio
async def test_list_drafts_word_count_from_file(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    content = "one two three four five"
    d = _draft_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "risk-level.md").write_text(content, encoding="utf-8")
    _seed_draft(factory, section="risk-level", status="draft")

    resp = await client.get(f"/api/v1/projects/{project_id}/reports/drafts")
    assert resp.status_code == 200
    by_section = {i["section"]: i for i in resp.json()}
    assert by_section["risk-level"]["word_count"] == 5
    assert by_section["risk-level"]["preview"] == content


@pytest.mark.asyncio
async def test_start_draft_returns_202(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    with patch("web.api.reports.start_draft_thread"):
        resp = await client.post(
            f"/api/v1/projects/{project_id}/reports/drafts",
            json={"section": "executive-summary", "force": False},
            headers=mut_headers,
        )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["section"] == "executive-summary"
    assert body["status"] == "generating"


@pytest.mark.asyncio
async def test_start_draft_returns_409_when_job_held(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    reg = get_registry()
    reg.acquire_job("report", "external-holder")
    try:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/reports/drafts",
            json={"section": "executive-summary"},
            headers=mut_headers,
        )
    finally:
        reg.release_job("report", "external-holder")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_ALREADY_RUNNING"


@pytest.mark.asyncio
async def test_start_draft_unknown_section_returns_422(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts",
        json={"section": "not-a-real-section"},
        headers=mut_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_draft_events_bus_filters_by_project_id(app_client) -> None:
    """Tail-mode behavior: subscribe to the report_draft stream and verify
    the filter the endpoint applies."""
    import asyncio
    from datetime import UTC, datetime

    from infrastructure.events.ids import new_event_id
    from infrastructure.events.types import BusEvent

    client, *_, project_id = app_client
    bus = client._transport.app.state.event_bus  # type: ignore[attr-defined]
    sub_id, queue = await bus.subscribe("report_draft")

    other = BusEvent(
        event_id=new_event_id(),
        job_id="report_draft",
        stream="report_draft",
        event_type="draft_started",
        payload={"section": "executive-summary", "project_id": 999},
        ts=datetime.now(UTC),
    )
    ours = BusEvent(
        event_id=new_event_id(),
        job_id="report_draft",
        stream="report_draft",
        event_type="draft_started",
        payload={"section": "risk-level", "project_id": project_id},
        ts=datetime.now(UTC),
    )
    await bus.publish(other)
    await bus.publish(ours)

    received: list[BusEvent] = []
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.5)
        except TimeoutError:
            break
        received.append(item)

    filtered = [i for i in received if i.payload.get("project_id") == project_id]
    assert len(filtered) == 1
    assert filtered[0].payload["section"] == "risk-level"

    await bus.unsubscribe("report_draft", sub_id)


@pytest.mark.asyncio
async def test_event_bus_has_report_draft_job_registered(app_client) -> None:
    """The report_draft job must be registered for SSE subscribers."""
    client, *_ = app_client
    bus = client._transport.app.state.event_bus  # type: ignore[attr-defined]
    sub_id, _queue = await bus.subscribe("report_draft")
    assert sub_id is not None
    await bus.unsubscribe("report_draft", sub_id)


# POST /reports/drafts/upload


@pytest.mark.asyncio
async def test_upload_draft_happy_path(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    content = "# Executive Summary\n\nThis is the draft.\n"
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts/upload",
        data={"section": "executive-summary"},
        files={"file": ("exec.md", content.encode("utf-8"), "text/markdown")},
        headers=mut_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["section"] == "executive-summary"
    assert body["status"] == "reviewed"
    assert body["original_filename"] == "exec.md"
    assert body["word_count"] > 0

    record = DraftRepository(factory).get("executive-summary")
    assert record is not None
    assert record.status == "reviewed"
    assert record.original_filename == "exec.md"

    out = _draft_dir(tmp_path) / "executive-summary.md"
    assert out.exists()
    assert out.read_text(encoding="utf-8") == content


@pytest.mark.asyncio
async def test_upload_draft_exceeds_1mib_returns_413(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    big = b"x" * (1024 * 1024 + 1)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts/upload",
        data={"section": "executive-summary"},
        files={"file": ("big.md", big, "text/plain")},
        headers=mut_headers,
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_draft_non_utf8_returns_422(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts/upload",
        data={"section": "executive-summary"},
        files={"file": ("binary.md", b"\xff\xfe\x00bad", "text/plain")},
        headers=mut_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_draft_null_byte_returns_422(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts/upload",
        data={"section": "executive-summary"},
        files={"file": ("nullbyte.md", b"Hello\x00World", "text/plain")},
        headers=mut_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_draft_bad_mime_returns_415(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts/upload",
        data={"section": "executive-summary"},
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
        headers=mut_headers,
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_draft_unknown_section_returns_422(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/drafts/upload",
        data={"section": "not-real"},
        files={"file": ("file.md", b"# Content", "text/markdown")},
        headers=mut_headers,
    )
    assert resp.status_code == 422


# GET /reports/drafts/{section}/download


@pytest.mark.asyncio
async def test_download_draft_returns_markdown(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    content = "# Risk Level\n\nHigh risks found.\n"
    d = _draft_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "risk-level.md").write_text(content, encoding="utf-8")
    _seed_draft(factory, section="risk-level", status="draft")

    resp = await client.get(
        f"/api/v1/projects/{project_id}/reports/drafts/risk-level/download"
    )
    assert resp.status_code == 200, resp.text
    assert "text/markdown" in resp.headers.get("content-type", "")
    assert resp.text == content


@pytest.mark.asyncio
async def test_download_draft_not_generated_returns_404(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(
        f"/api/v1/projects/{project_id}/reports/drafts/executive-summary/download"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_draft_unknown_section_returns_422(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(
        f"/api/v1/projects/{project_id}/reports/drafts/not-real/download"
    )
    assert resp.status_code == 422


# DELETE /reports/drafts/{section}


@pytest.mark.asyncio
async def test_delete_draft_returns_204_and_removes_file(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    d = _draft_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "executive-summary.md").write_text("content", encoding="utf-8")
    _seed_draft(factory, section="executive-summary", status="draft")

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/reports/drafts/executive-summary",
        headers=mut_headers,
    )
    assert resp.status_code == 204

    assert DraftRepository(factory).get("executive-summary") is None
    assert not (d / "executive-summary.md").exists()


@pytest.mark.asyncio
async def test_delete_draft_idempotent_when_not_present(app_client) -> None:
    """DELETE on a non-existent section returns 204 without error."""
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.delete(
        f"/api/v1/projects/{project_id}/reports/drafts/executive-summary",
        headers=mut_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_draft_unknown_section_returns_422(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.delete(
        f"/api/v1/projects/{project_id}/reports/drafts/not-real",
        headers=mut_headers,
    )
    assert resp.status_code == 422
