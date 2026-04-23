"""LockQueryService — read-only facade over LockRegistry for ports."""

from __future__ import annotations

from application.locking.registry import LockRegistry, get_registry


class LockQueryService:
    def __init__(self, registry: LockRegistry | None = None) -> None:
        self._registry = registry if registry is not None else get_registry()

    def snapshot(self) -> tuple[dict[str, str], dict[int, str]]:
        return self._registry.snapshot()

    def is_finding_locked(self, finding_id: int) -> bool:
        return self._registry.is_finding_locked(finding_id)

    def finding_lock_holder(self, finding_id: int) -> str | None:
        return self._registry.finding_lock_holder(finding_id)
