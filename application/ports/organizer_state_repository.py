"""Port for tracking ingested Burp Organizer item IDs."""

from __future__ import annotations

from typing import Protocol


class OrganizerStateRepositoryPort(Protocol):
    def get_ingested_ids(self, project_id: int) -> set[int]: ...
    def mark_ingested(self, project_id: int, item_id: int) -> None: ...
