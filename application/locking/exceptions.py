from __future__ import annotations


class LockError(Exception):
    """Base class for all locking errors."""


class JobBusy(LockError):
    """Tier-1 job slot is already held by another caller."""

    def __init__(self, kind: str, current_holder: str) -> None:
        self.kind = kind
        self.current_holder = current_holder
        super().__init__(f"job slot '{kind}' is already held by '{current_holder}'")


class FindingsBusy(LockError):
    """Tier-2 atomic acquire hit one or more already-locked finding ids."""

    def __init__(
        self,
        conflicting_ids: list[int],
        holders: dict[int, str],
    ) -> None:
        self.conflicting_ids = sorted(conflicting_ids)
        self.holders = dict(holders)
        super().__init__(f"finding ids already locked: {self.conflicting_ids}")


class HolderMismatch(LockError):
    """Release attempted by a caller that does not hold the resource."""

    def __init__(
        self,
        resource: str,
        expected: str,
        actual: str,
    ) -> None:
        self.resource = resource
        self.expected = expected
        self.actual = actual
        super().__init__(f"{resource}: held by '{actual}', not '{expected}'")
