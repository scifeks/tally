from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Literal, cast

from application.locking.exceptions import FindingsBusy, HolderMismatch, JobBusy

type JobKind = Literal["scan", "triage", "report"]


class LockRegistry:
    """Process-global two-tier in-memory lock registry.

    Tier 1 — Job slots: at most one of ``scan`` / ``triage`` / ``report``
    active at a time. Starting a second instance of the same kind fails fast.

    Tier 2 — Finding-id registry: atomic all-or-nothing acquisition over a
    set of finding ids, sorted ascending to prevent ordering-based deadlocks.

    A single ``threading.Lock`` guards both tiers. All public methods are
    synchronous. Async callers wrap at the adapter boundary via
    ``asyncio.to_thread`` if needed.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._jobs: dict[str, str] = {}  # kind -> holder_token
        self._findings: dict[int, str] = {}  # finding_id -> holder_token

    # ── Tier 1: job slots ────────────────────────────────────────────────────

    def acquire_job(self, kind: JobKind, holder_token: str) -> None:
        """Claim the single slot for *kind*. Raises :exc:`JobBusy` if held."""
        with self._guard:
            if kind in self._jobs:
                raise JobBusy(kind, self._jobs[kind])
            self._jobs[kind] = holder_token

    def release_job(self, kind: JobKind, holder_token: str) -> None:
        """Release the slot for *kind*.

        Raises :exc:`HolderMismatch` if *holder_token* is not the current
        holder. Raises :exc:`KeyError` if the slot is not held at all.
        """
        with self._guard:
            if kind not in self._jobs:
                raise KeyError(f"job slot '{kind}' is not held")
            if self._jobs[kind] != holder_token:
                raise HolderMismatch(f"job:{kind}", holder_token, self._jobs[kind])
            del self._jobs[kind]

    def current_job_holder(self, kind: JobKind) -> str | None:
        """Return the current holder token for *kind*, or ``None``."""
        with self._guard:
            return self._jobs.get(kind)

    # ── Tier 2: finding-id set ───────────────────────────────────────────────

    def acquire_findings(
        self,
        finding_ids: Iterable[int],
        holder_token: str,
    ) -> None:
        """Atomically claim every id in *finding_ids*.

        Sorts and de-duplicates ids before inspection. If any id is already
        held, raises :exc:`FindingsBusy` with the conflicting ids and their
        current holders, and claims *nothing* (all-or-nothing semantics).
        """
        ids = sorted(set(finding_ids))
        if not ids:
            return
        with self._guard:
            conflicts: dict[int, str] = {
                fid: self._findings[fid] for fid in ids if fid in self._findings
            }
            if conflicts:
                raise FindingsBusy(
                    conflicting_ids=list(conflicts),
                    holders=conflicts,
                )
            for fid in ids:
                self._findings[fid] = holder_token

    def release_findings(
        self,
        finding_ids: Iterable[int],
        holder_token: str,
    ) -> None:
        """Release every id in *finding_ids* held by *holder_token*.

        Unknown ids are silently skipped (idempotent cleanup). If any id is
        held by a different token, raises :exc:`HolderMismatch`; ids already
        released in the same call remain released.
        """
        ids = sorted(set(finding_ids))
        with self._guard:
            for fid in ids:
                if fid not in self._findings:
                    continue
                if self._findings[fid] != holder_token:
                    raise HolderMismatch(
                        f"finding:{fid}", holder_token, self._findings[fid]
                    )
                del self._findings[fid]

    def is_finding_locked(self, finding_id: int) -> bool:
        """Return ``True`` iff *finding_id* has a current holder."""
        with self._guard:
            return finding_id in self._findings

    def finding_lock_holder(self, finding_id: int) -> str | None:
        """Return the holder token for *finding_id*, or ``None`` if unlocked."""
        with self._guard:
            return self._findings.get(finding_id)

    def assert_held_by(self, finding_id: int, holder_token: str) -> None:
        """Assert that *finding_id* is currently held by *holder_token*.

        Raises :exc:`HolderMismatch` if held by a different token or not held.
        """
        with self._guard:
            actual = self._findings.get(finding_id)
        if actual != holder_token:
            raise HolderMismatch(
                f"finding:{finding_id}",
                expected=holder_token,
                actual=actual or "<not held>",
            )

    # ── Context managers ─────────────────────────────────────────────────────

    @contextmanager
    def job(self, kind: JobKind, holder_token: str) -> Iterator[None]:
        """Acquire a Tier-1 job slot and release it on context exit."""
        self.acquire_job(kind, holder_token)
        try:
            yield
        finally:
            self.release_job(kind, holder_token)

    @contextmanager
    def findings(
        self,
        finding_ids: Iterable[int],
        holder_token: str,
    ) -> Iterator[None]:
        """Acquire a Tier-2 finding-id set and release it on context exit."""
        ids = list(finding_ids)
        self.acquire_findings(ids, holder_token)
        try:
            yield
        finally:
            self.release_findings(ids, holder_token)

    # ── Test fixture support ──────────────────────────────────────────────────

    def snapshot(self) -> tuple[dict[str, str], dict[int, str]]:
        """Return a shallow copy of current registry state for test isolation."""
        with self._guard:
            return dict(self._jobs), dict(self._findings)

    def restore(self, snap: tuple[dict[str, str], dict[int, str]]) -> None:
        """Restore registry state from a prior :meth:`snapshot`."""
        jobs, findings = snap
        with self._guard:
            self._jobs.clear()
            self._jobs.update(jobs)
            self._findings.clear()
            self._findings.update(findings)

    def reset(self) -> None:
        """Clear all state. Intended for test use only."""
        with self._guard:
            self._jobs.clear()
            self._findings.clear()


# ── Process-global singleton ──────────────────────────────────────────────────

_registry: LockRegistry | None = None


def get_registry() -> LockRegistry:
    """Return the process-global :class:`LockRegistry`, creating it lazily."""
    global _registry
    if _registry is None:
        _registry = LockRegistry()
    return cast(LockRegistry, _registry)
