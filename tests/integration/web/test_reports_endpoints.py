"""Integration tests for the Phase 7 report endpoints."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.locking import get_registry
from infrastructure.store.repositories.reports import ReportRepository
from web.adapters.report_run_registry import get_report_run_registry

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_report_state():
    """Reset process-singleton report state between tests."""
    get_report_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("report") is not None:  # type: ignore[attr-defined]
        reg._jobs["report"] = None  # type: ignore[attr-defined,index]
    yield
    get_report_run_registry().reset()
    if reg._jobs.get("report") is not None:  # type: ignore[attr-defined]
        reg._jobs["report"] = None  # type: ignore[attr-defined,index]


def _seed_report(
    factory,
    *,
    project_id: int,
    filepath: str,
    filename: str = "report.pdf",
    fmt: str = "pdf",
    status: str = "done",
    pinned: bool = False,
    file_size: int | None = 1024,
) -> int:
    """Insert a reports row directly and return its id."""
    repo = ReportRepository(factory)
    rid = repo.create(
        project_id=project_id,
        scan_run_id=None,
        format=fmt,
        filename=filename,
        filepath=filepath,
        status=status,
        retention_tier="pinned" if pinned else "auto",
    )
    if status == "done":
        repo.set_finished_at(rid, datetime.now(UTC).isoformat())
        if file_size is not None:
            repo.set_file_size(rid, file_size)
    return rid


@pytest.mark.asyncio
async def test_history_empty_returns_200(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/reports")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_history_lists_reports_newest_first(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    p1 = tmp_path / "projects" / "testproject" / "reports" / "first.pdf"
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_bytes(b"%PDF1")
    p2 = tmp_path / "projects" / "testproject" / "reports" / "second.pdf"
    p2.write_bytes(b"%PDF2")

    a = _seed_report(factory, project_id=project_id, filepath=str(p1))
    b = _seed_report(factory, project_id=project_id, filepath=str(p2))

    resp = await client.get(f"/api/v1/projects/{project_id}/reports")
    assert resp.status_code == 200
    body = resp.json()
    ids = [item["id"] for item in body["items"]]
    assert ids == [b, a]
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_history_pagination(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        path = base / f"r{i}.pdf"
        path.write_bytes(b"%PDF")
        _seed_report(factory, project_id=project_id, filepath=str(path))

    resp = await client.get(
        f"/api/v1/projects/{project_id}/reports",
        params={"offset": 1, "limit": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["offset"] == 1
    assert body["limit"] == 1


@pytest.mark.asyncio
async def test_history_unknown_project_returns_404(app_client) -> None:
    client, *_ = app_client
    resp = await client.get("/api/v1/projects/9999/reports")
    assert resp.status_code == 404


# GET /reports/latest


@pytest.mark.asyncio
async def test_latest_returns_null_when_no_reports(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/reports/latest")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_latest_returns_most_recent_done_report(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    older = base / "older.pdf"
    older.write_bytes(b"%PDF")
    _seed_report(factory, project_id=project_id, filepath=str(older))
    newer = base / "newer.pdf"
    newer.write_bytes(b"%PDF")
    newer_id = _seed_report(factory, project_id=project_id, filepath=str(newer))

    resp = await client.get(f"/api/v1/projects/{project_id}/reports/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == newer_id
    assert body["status"] == "done"


# GET /reports/{id}/download


@pytest.mark.asyncio
async def test_download_streams_file_with_attachment_header(
    app_client, tmp_path
) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "ready.pdf"
    target.write_bytes(b"%PDFCONTENT")
    rid = _seed_report(
        factory, project_id=project_id, filepath=str(target), filename="ready.pdf"
    )

    resp = await client.get(f"/api/v1/projects/{project_id}/reports/{rid}/download")
    assert resp.status_code == 200
    assert resp.content == b"%PDFCONTENT"
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "ready.pdf" in resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_download_rejects_path_traversal(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    # Filepath outside the project's reports directory.
    outside = tmp_path / "elsewhere" / "secrets.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"secret")
    rid = _seed_report(
        factory,
        project_id=project_id,
        filepath=str(outside),
        filename="secrets.txt",
    )
    resp = await client.get(f"/api/v1/projects/{project_id}/reports/{rid}/download")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "PATH_TRAVERSAL"


@pytest.mark.asyncio
async def test_download_404_when_report_missing(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/reports/999/download")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_409_when_status_not_done(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "queued.pdf"
    rid = _seed_report(
        factory,
        project_id=project_id,
        filepath=str(target),
        status="queued",
        file_size=None,
    )
    resp = await client.get(f"/api/v1/projects/{project_id}/reports/{rid}/download")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "REPORT_NOT_READY"


# Pin / delete


@pytest.mark.asyncio
async def test_pin_marks_report_pinned(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "pinme.pdf"
    target.write_bytes(b"%PDF")
    rid = _seed_report(factory, project_id=project_id, filepath=str(target))

    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/{rid}/pin",
        headers=mut_headers,
    )
    assert resp.status_code == 204

    listing = await client.get(f"/api/v1/projects/{project_id}/reports")
    item = listing.json()["items"][0]
    assert item["pinned"] is True


@pytest.mark.asyncio
async def test_delete_pinned_returns_409(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "stuck.pdf"
    target.write_bytes(b"%PDF")
    rid = _seed_report(
        factory, project_id=project_id, filepath=str(target), pinned=True
    )

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/reports/{rid}",
        headers=mut_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "REPORT_PINNED"


@pytest.mark.asyncio
async def test_delete_unlinks_file_and_row(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "byebye.pdf"
    target.write_bytes(b"%PDF")
    rid = _seed_report(factory, project_id=project_id, filepath=str(target))

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/reports/{rid}",
        headers=mut_headers,
    )
    assert resp.status_code == 204
    assert not target.exists()

    repo = ReportRepository(factory)
    assert repo.get(rid) is None


# Cancel


@pytest.mark.asyncio
async def test_cancel_returns_409_when_not_running(app_client, tmp_path) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    base = tmp_path / "projects" / "testproject" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "done.pdf"
    target.write_bytes(b"%PDF")
    rid = _seed_report(factory, project_id=project_id, filepath=str(target))

    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/{rid}/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "REPORT_NOT_CANCELLABLE"


@pytest.mark.asyncio
async def test_cancel_404_when_report_missing(app_client) -> None:
    client, *_, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/999/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_returns_409_when_job_held(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    reg = get_registry()
    reg.acquire_job("report", "external-holder")
    try:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/reports/generate",
            json={"format": "json"},
            headers=mut_headers,
        )
    finally:
        reg.release_job("report", "external-holder")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_ALREADY_RUNNING"


@pytest.mark.asyncio
async def test_generate_validates_format(app_client) -> None:
    client, *_, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/generate",
        json={"format": "docx"},
        headers=mut_headers,
    )
    assert resp.status_code == 422


async def _wait_for_assembler_call(mock_class: MagicMock, timeout: float = 5.0) -> None:
    """Poll until the patched ReportAssembler class is invoked once,
    then drain the report daemon thread so its event-bus publishes
    are processed before the test's event loop tears down."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if mock_class.call_count >= 1:
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError(
            f"ReportAssembler was not called within {timeout}s "
            f"(call_count={mock_class.call_count})"
        )
    while asyncio.get_event_loop().time() < deadline:
        if not any(t.name.startswith("report-run-") for t in threading.enumerate()):
            return
        await asyncio.sleep(0.05)


def _patch_assembler(monkeypatch) -> MagicMock:
    """Replace ReportAssembler with a Mock returning bytes from render_pdf.

    Returns the patched class so callers can inspect its constructor kwargs.
    The mock is patched on the source module because ``_run_pdf`` lazy-imports
    via ``from application.reporting import assembler as assembler_mod``.
    """
    instance = MagicMock()
    instance.render_pdf.return_value = b"fake-pdf-bytes"
    mock_class = MagicMock(return_value=instance)
    monkeypatch.setattr("application.reporting.assembler.ReportAssembler", mock_class)
    return mock_class


@pytest.mark.asyncio
async def test_generate_passes_company_name_override_to_assembler(
    app_client, monkeypatch
) -> None:
    client, *_, mut_headers, project_id = app_client
    mock_class = _patch_assembler(monkeypatch)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/generate",
        json={"format": "pdf", "company_name": "ACME"},
        headers=mut_headers,
    )
    assert resp.status_code == 202

    await _wait_for_assembler_call(mock_class)
    kwargs = mock_class.call_args.kwargs
    assert kwargs["company_name_override"] == "ACME"
    assert kwargs["skip_triage"] is False


@pytest.mark.asyncio
async def test_generate_passes_company_name_camel_case_alias(
    app_client, monkeypatch
) -> None:
    client, *_, mut_headers, project_id = app_client
    mock_class = _patch_assembler(monkeypatch)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/generate",
        json={"format": "pdf", "companyName": "ACME"},
        headers=mut_headers,
    )
    assert resp.status_code == 202

    await _wait_for_assembler_call(mock_class)
    kwargs = mock_class.call_args.kwargs
    assert kwargs["company_name_override"] == "ACME"


@pytest.mark.asyncio
async def test_generate_passes_skip_triage_true_to_assembler(
    app_client, monkeypatch
) -> None:
    client, *_, mut_headers, project_id = app_client
    mock_class = _patch_assembler(monkeypatch)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/generate",
        json={"format": "pdf", "skip_triage": True},
        headers=mut_headers,
    )
    assert resp.status_code == 202

    await _wait_for_assembler_call(mock_class)
    kwargs = mock_class.call_args.kwargs
    assert kwargs["skip_triage"] is True
    assert kwargs["company_name_override"] is None


@pytest.mark.asyncio
async def test_generate_defaults_when_neither_field_sent(
    app_client, monkeypatch
) -> None:
    client, *_, mut_headers, project_id = app_client
    mock_class = _patch_assembler(monkeypatch)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/reports/generate",
        json={"format": "pdf"},
        headers=mut_headers,
    )
    assert resp.status_code == 202

    await _wait_for_assembler_call(mock_class)
    kwargs = mock_class.call_args.kwargs
    assert kwargs["company_name_override"] is None
    assert kwargs["skip_triage"] is False


# Repository unit tests for retention


def test_retention_keeps_pinned_and_drops_oldest(tmp_path: Path) -> None:
    from infrastructure.store.connection import ConnectionFactory

    db = tmp_path / "findings.db"
    factory = ConnectionFactory(db)
    factory.init_schema()
    repo = ReportRepository(factory)

    pid = 1
    ids = []
    for i in range(5):
        rid = repo.create(
            project_id=pid,
            scan_run_id=None,
            format="pdf",
            filename=f"r{i}.pdf",
            filepath=f"/tmp/r{i}.pdf",
        )
        repo.set_status(rid, "done")
        repo.set_finished_at(rid)
        ids.append(rid)

    # Pin the very first (oldest) report
    repo.set_pinned(ids[0], True)

    # Keep only 2 most recent → expect rows ids[1] and ids[2] returned to delete
    selected = repo.select_for_retention(pid, keep=2)
    selected_ids = sorted(r.id for r in selected)
    assert selected_ids == sorted([ids[1], ids[2]])
