"""Application-layer errors for saved scans that carry typed payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.saved_scans.entry import StaleSavedScanItem


class StaleSavedScanError(Exception):
    """Raised when a saved scan references items that no longer resolve.

    Carries one entry per stale reference for the route layer to surface
    in the D-1-7 STALE_SAVED_SCAN envelope.
    """

    def __init__(self, stale_items: list[StaleSavedScanItem]) -> None:
        self.stale_items: tuple[StaleSavedScanItem, ...] = tuple(stale_items)
        super().__init__(f"saved scan has {len(self.stale_items)} stale reference(s)")
