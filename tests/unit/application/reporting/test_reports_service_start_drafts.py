"""Unit tests for ReportsService.start_drafts and the batch worker.

Covers the synchronous portion of ``start_drafts`` (validation, lock
acquisition, handle shape) by stubbing the worker so the lock stays
held and we can assert behaviour cleanly. Worker semantics
(per-section register/unregister, per-section failure isolation, lock
release on completion) are exercised by calling ``_run_worker``
directly with a mocked ``run_draft``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.locking.exceptions import JobBusy
from application.locking.registry import LockRegistry
from application.reporting.draft_orchestrator import DraftOverwriteDenied
from application.reporting.draft_run_registry import DraftRunRegistry
from application.reporting.reports_service import (
    DraftBatchHandle,
    ReportsService,
    UnknownSectionError,
)


@pytest.fixture
def registry() -> LockRegistry:
    return LockRegistry()


@pytest.fixture
def draft_run_registry() -> DraftRunRegistry:
    return DraftRunRegistry()


@pytest.fixture
def service(
    registry: LockRegistry, draft_run_registry: DraftRunRegistry
) -> ReportsService:
    svc = ReportsService(
        report_repo=MagicMock(),
        draft_repo=MagicMock(),
        lock_registry=registry,
        draft_run_registry=draft_run_registry,
    )
    svc._run_worker = MagicMock()  # type: ignore[method-assign]
    return svc


def _start_kwargs(sections: list[str]) -> dict:
    return dict(
        sections=sections,
        force=False,
        base_path="/tmp",
        project_id=1,
        project_name="proj",
        prompt=MagicMock(),
        event_sink=MagicMock(),
    )


def test_single_section_returns_handle_and_holds_lock(
    service: ReportsService, registry: LockRegistry
) -> None:
    handle = service.start_drafts(**_start_kwargs(["executive-summary"]))

    assert isinstance(handle, DraftBatchHandle)
    assert handle.sections == ("executive-summary",)
    assert handle.holder_token.startswith("draft-batch:")
    assert registry.current_job_holder("report") == handle.holder_token


def test_multi_section_returns_handle_in_order(
    service: ReportsService,
) -> None:
    handle = service.start_drafts(
        **_start_kwargs(["executive-summary", "risk-level", "critical-issues"])
    )
    assert handle.sections == (
        "executive-summary",
        "risk-level",
        "critical-issues",
    )


def test_second_start_raises_job_busy_synchronously(
    service: ReportsService,
) -> None:
    service.start_drafts(**_start_kwargs(["executive-summary"]))
    with pytest.raises(JobBusy):
        service.start_drafts(**_start_kwargs(["risk-level"]))


def test_empty_sections_raises_and_does_not_acquire_lock(
    service: ReportsService, registry: LockRegistry
) -> None:
    with pytest.raises(UnknownSectionError):
        service.start_drafts(**_start_kwargs([]))
    assert registry.current_job_holder("report") is None


def test_duplicate_section_raises_and_does_not_acquire_lock(
    service: ReportsService, registry: LockRegistry
) -> None:
    with pytest.raises(UnknownSectionError):
        service.start_drafts(
            **_start_kwargs(["executive-summary", "executive-summary"])
        )
    assert registry.current_job_holder("report") is None


def test_unknown_section_raises_and_does_not_acquire_lock(
    service: ReportsService, registry: LockRegistry
) -> None:
    with pytest.raises(UnknownSectionError):
        service.start_drafts(**_start_kwargs(["not-a-real-section"]))
    assert registry.current_job_holder("report") is None


# Worker-level tests: drive _run_worker synchronously by stubbing run_draft.


def _run_worker_kwargs(sections: tuple[str, ...]) -> dict:
    return dict(
        sections=sections,
        force=False,
        skip_triage=False,
        base_path="/tmp",
        project_id=1,
        project_name="proj",
        holder_token="draft-batch:test1234",
        prompt=MagicMock(),
        event_sink=MagicMock(),
    )


def test_worker_releases_lock_after_loop(
    registry: LockRegistry, draft_run_registry: DraftRunRegistry, monkeypatch
) -> None:
    svc = ReportsService(
        report_repo=MagicMock(),
        draft_repo=MagicMock(),
        lock_registry=registry,
        draft_run_registry=draft_run_registry,
    )
    monkeypatch.setattr(
        "application.reporting.reports_service.run_draft",
        MagicMock(),
    )
    registry.acquire_job("report", "draft-batch:test1234")
    svc._run_worker(**_run_worker_kwargs(("executive-summary", "risk-level")))
    assert registry.current_job_holder("report") is None


def test_worker_continues_after_per_section_failure(
    registry: LockRegistry, draft_run_registry: DraftRunRegistry, monkeypatch
) -> None:
    """A section raising an exception must not abort the rest of the batch."""
    svc = ReportsService(
        report_repo=MagicMock(),
        draft_repo=MagicMock(),
        lock_registry=registry,
        draft_run_registry=draft_run_registry,
    )
    calls: list[str] = []

    def fake_run_draft(req, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(req.section)
        if req.section == "risk-level":
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "application.reporting.reports_service.run_draft", fake_run_draft
    )
    registry.acquire_job("report", "draft-batch:test1234")
    svc._run_worker(
        **_run_worker_kwargs(("executive-summary", "risk-level", "critical-issues"))
    )
    assert calls == ["executive-summary", "risk-level", "critical-issues"]
    assert registry.current_job_holder("report") is None


def test_worker_treats_overwrite_denied_as_skip(
    registry: LockRegistry, draft_run_registry: DraftRunRegistry, monkeypatch
) -> None:
    """DraftOverwriteDenied for one section must not abort the rest."""
    svc = ReportsService(
        report_repo=MagicMock(),
        draft_repo=MagicMock(),
        lock_registry=registry,
        draft_run_registry=draft_run_registry,
    )
    calls: list[str] = []

    def fake_run_draft(req, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(req.section)
        if req.section == "executive-summary":
            raise DraftOverwriteDenied("exists")

    monkeypatch.setattr(
        "application.reporting.reports_service.run_draft", fake_run_draft
    )
    registry.acquire_job("report", "draft-batch:test1234")
    svc._run_worker(**_run_worker_kwargs(("executive-summary", "risk-level")))
    assert calls == ["executive-summary", "risk-level"]


def test_worker_unregisters_each_section_after_run(
    registry: LockRegistry, draft_run_registry: DraftRunRegistry, monkeypatch
) -> None:
    svc = ReportsService(
        report_repo=MagicMock(),
        draft_repo=MagicMock(),
        lock_registry=registry,
        draft_run_registry=draft_run_registry,
    )
    monkeypatch.setattr(
        "application.reporting.reports_service.run_draft",
        MagicMock(),
    )
    registry.acquire_job("report", "draft-batch:test1234")
    svc._run_worker(**_run_worker_kwargs(("executive-summary", "risk-level")))
    assert draft_run_registry.list_all() == []


def test_worker_threads_skip_triage_into_draft_request(
    registry: LockRegistry, draft_run_registry: DraftRunRegistry, monkeypatch
) -> None:
    """skip_triage on the batch must propagate into every DraftRequest."""
    svc = ReportsService(
        report_repo=MagicMock(),
        draft_repo=MagicMock(),
        lock_registry=registry,
        draft_run_registry=draft_run_registry,
    )
    seen: list[bool] = []

    def fake_run_draft(req, **_kwargs):  # type: ignore[no-untyped-def]
        seen.append(req.skip_triage)

    monkeypatch.setattr(
        "application.reporting.reports_service.run_draft", fake_run_draft
    )
    registry.acquire_job("report", "draft-batch:test1234")
    kwargs = _run_worker_kwargs(("executive-summary", "risk-level"))
    kwargs["skip_triage"] = True
    svc._run_worker(**kwargs)
    assert seen == [True, True]
