"""Unit tests for LockQueryService."""

from __future__ import annotations

import pytest

from application.locking.query_service import LockQueryService
from application.locking.registry import LockRegistry, get_registry


@pytest.fixture
def reg() -> LockRegistry:
    return LockRegistry()


@pytest.fixture
def svc(reg: LockRegistry) -> LockQueryService:
    return LockQueryService(reg)


def test_is_finding_locked_false_when_unlocked(svc: LockQueryService) -> None:
    assert svc.is_finding_locked(42) is False


def test_is_finding_locked_true_when_locked(
    svc: LockQueryService, reg: LockRegistry
) -> None:
    reg.acquire_findings([42], "tok-a")
    assert svc.is_finding_locked(42) is True


def test_is_finding_locked_false_after_release(
    svc: LockQueryService, reg: LockRegistry
) -> None:
    reg.acquire_findings([42], "tok-a")
    reg.release_findings([42], "tok-a")
    assert svc.is_finding_locked(42) is False


def test_finding_lock_holder_none_when_unlocked(svc: LockQueryService) -> None:
    assert svc.finding_lock_holder(99) is None


def test_finding_lock_holder_returns_token(
    svc: LockQueryService, reg: LockRegistry
) -> None:
    reg.acquire_findings([99], "my-holder")
    assert svc.finding_lock_holder(99) == "my-holder"


def test_snapshot_includes_finding_locks(
    svc: LockQueryService, reg: LockRegistry
) -> None:
    reg.acquire_findings([7, 8], "tok-b")
    _, findings_snap = svc.snapshot()
    assert findings_snap[7] == "tok-b"
    assert findings_snap[8] == "tok-b"


def test_snapshot_includes_job_locks(svc: LockQueryService, reg: LockRegistry) -> None:
    reg.acquire_job("triage", "job-tok")
    jobs_snap, _ = svc.snapshot()
    assert jobs_snap["triage"] == "job-tok"


def test_snapshot_is_shallow_copy(svc: LockQueryService, reg: LockRegistry) -> None:
    reg.acquire_findings([3], "tok-c")
    _, findings_snap = svc.snapshot()
    findings_snap.clear()
    assert svc.is_finding_locked(3) is True


def test_defaults_to_process_global_registry() -> None:
    svc1 = LockQueryService()
    svc2 = LockQueryService()
    assert svc1._registry is svc2._registry
    assert svc1._registry is get_registry()
