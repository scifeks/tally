from __future__ import annotations

import threading

import pytest

from application.locking.exceptions import FindingsBusy, HolderMismatch, JobBusy
from application.locking.registry import LockRegistry, get_registry


@pytest.fixture
def reg() -> LockRegistry:
    """Fresh LockRegistry for each test."""
    return LockRegistry()


# ── Tier 1: job slots ─────────────────────────────────────────────────────────


def test_acquire_job_success_then_release(reg: LockRegistry) -> None:
    reg.acquire_job("scan", "tok-1")
    assert reg.current_job_holder("scan") == "tok-1"
    reg.release_job("scan", "tok-1")
    assert reg.current_job_holder("scan") is None


def test_acquire_job_rejects_second_same_kind(reg: LockRegistry) -> None:
    reg.acquire_job("scan", "tok-1")
    with pytest.raises(JobBusy) as exc_info:
        reg.acquire_job("scan", "tok-2")
    assert exc_info.value.kind == "scan"
    assert exc_info.value.current_holder == "tok-1"


def test_acquire_job_allows_different_kinds_concurrently(reg: LockRegistry) -> None:
    reg.acquire_job("scan", "s-tok")
    reg.acquire_job("triage", "t-tok")
    reg.acquire_job("report", "r-tok")
    assert reg.current_job_holder("scan") == "s-tok"
    assert reg.current_job_holder("triage") == "t-tok"
    assert reg.current_job_holder("report") == "r-tok"


def test_release_job_rejects_non_holder(reg: LockRegistry) -> None:
    reg.acquire_job("scan", "real-tok")
    with pytest.raises(HolderMismatch):
        reg.release_job("scan", "wrong-tok")
    assert reg.current_job_holder("scan") == "real-tok"


def test_release_job_unheld_raises_keyerror(reg: LockRegistry) -> None:
    with pytest.raises(KeyError):
        reg.release_job("scan", "any-tok")


# ── Tier 2: finding-id set ────────────────────────────────────────────────────


def test_acquire_findings_single_id_success(reg: LockRegistry) -> None:
    reg.acquire_findings([42], "holder-a")
    assert reg.is_finding_locked(42)
    assert reg.finding_lock_holder(42) == "holder-a"
    reg.release_findings([42], "holder-a")
    assert not reg.is_finding_locked(42)
    assert reg.finding_lock_holder(42) is None


def test_acquire_findings_empty_input_is_noop(reg: LockRegistry) -> None:
    reg.acquire_findings([], "holder-a")  # no exception is sufficient


def test_acquire_findings_deduplicates_input(reg: LockRegistry) -> None:
    reg.acquire_findings([3, 3, 5], "holder-a")
    assert reg.is_finding_locked(3)
    assert reg.is_finding_locked(5)
    reg.release_findings([3, 5], "holder-a")
    assert not reg.is_finding_locked(3)


def test_acquire_findings_atomic_rollback_on_collision(reg: LockRegistry) -> None:
    reg.acquire_findings([7], "holder-a")
    with pytest.raises(FindingsBusy) as exc_info:
        reg.acquire_findings([5, 7, 9], "holder-b")
    assert 7 in exc_info.value.conflicting_ids
    assert not reg.is_finding_locked(5)
    assert not reg.is_finding_locked(9)
    assert reg.is_finding_locked(7)


def test_findings_busy_exposes_holders_dict(reg: LockRegistry) -> None:
    reg.acquire_findings([7], "holder-a")
    with pytest.raises(FindingsBusy) as exc_info:
        reg.acquire_findings([5, 7, 9], "holder-b")
    assert exc_info.value.holders == {7: "holder-a"}


def test_release_findings_holder_only(reg: LockRegistry) -> None:
    reg.acquire_findings([1, 2, 3], "holder-a")
    with pytest.raises(HolderMismatch):
        reg.release_findings([1, 2, 3], "holder-b")
    assert reg.is_finding_locked(1)
    assert reg.is_finding_locked(2)
    assert reg.is_finding_locked(3)
    reg.release_findings([1, 2, 3], "holder-a")
    assert not reg.is_finding_locked(1)


def test_release_findings_idempotent_on_unknown_ids(reg: LockRegistry) -> None:
    reg.release_findings([100, 200], "any-tok")


# ── Threading: sorted-id contention ──────────────────────────────────────────


def test_sorted_acquire_order_two_thread_contention(reg: LockRegistry) -> None:
    """Both threads race; exactly one must succeed and the other get FindingsBusy."""
    results: dict[str, bool | FindingsBusy] = {}
    barrier = threading.Barrier(2)

    def attempt(name: str, ids: list[int], token: str) -> None:
        barrier.wait()
        try:
            reg.acquire_findings(ids, token)
            results[name] = True
        except FindingsBusy as exc:
            results[name] = exc

    for _ in range(50):
        reg.reset()
        results.clear()
        t1 = threading.Thread(target=attempt, args=("t1", [1, 2, 3, 4], "tok-1"))
        t2 = threading.Thread(target=attempt, args=("t2", [3, 4, 5, 6], "tok-2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [k for k, v in results.items() if v is True]
        failures = [k for k, v in results.items() if isinstance(v, FindingsBusy)]
        assert len(successes) == 1, f"Expected exactly one success, got {results}"
        assert len(failures) == 1, f"Expected exactly one failure, got {results}"
        loser = failures[0]
        loser_ids = [1, 2, 3, 4] if loser == "t1" else [3, 4, 5, 6]
        winner_tok = "tok-2" if loser == "t1" else "tok-1"
        for fid in loser_ids:
            holder = reg.finding_lock_holder(fid)
            assert holder is None or holder == winner_tok


# ── Context managers ──────────────────────────────────────────────────────────


def test_context_manager_job_releases_on_exception(reg: LockRegistry) -> None:
    with pytest.raises(RuntimeError):
        with reg.job("scan", "tok-1"):
            raise RuntimeError("boom")
    assert reg.current_job_holder("scan") is None


def test_context_manager_findings_releases_on_exception(reg: LockRegistry) -> None:
    with pytest.raises(RuntimeError):
        with reg.findings([10, 20], "tok-1"):
            raise RuntimeError("boom")
    assert not reg.is_finding_locked(10)
    assert not reg.is_finding_locked(20)


# ── Query helpers ─────────────────────────────────────────────────────────────


def test_is_finding_locked_and_holder_queries(reg: LockRegistry) -> None:
    assert not reg.is_finding_locked(99)
    assert reg.finding_lock_holder(99) is None
    reg.acquire_findings([99], "holder-x")
    assert reg.is_finding_locked(99)
    assert reg.finding_lock_holder(99) == "holder-x"
    reg.release_findings([99], "holder-x")
    assert not reg.is_finding_locked(99)


# ── Test-fixture support ──────────────────────────────────────────────────────


def test_reset_clears_all_state(reg: LockRegistry) -> None:
    reg.acquire_job("scan", "tok-1")
    reg.acquire_findings([1, 2], "tok-2")
    reg.reset()
    assert reg.current_job_holder("scan") is None
    assert not reg.is_finding_locked(1)
    assert not reg.is_finding_locked(2)


def test_snapshot_restore_roundtrip(reg: LockRegistry) -> None:
    reg.acquire_job("triage", "tok-t")
    reg.acquire_findings([5, 6], "tok-f")
    snap = reg.snapshot()
    reg.reset()
    assert reg.current_job_holder("triage") is None
    reg.restore(snap)
    assert reg.current_job_holder("triage") == "tok-t"
    assert reg.is_finding_locked(5)
    assert reg.is_finding_locked(6)


# ── Singleton ─────────────────────────────────────────────────────────────────


def test_get_registry_returns_singleton() -> None:
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2
    r1.acquire_job("scan", "test-tok")
    assert r2.current_job_holder("scan") == "test-tok"
    r1.release_job("scan", "test-tok")
