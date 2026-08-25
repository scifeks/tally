"""Persist ingested Burp Organizer item IDs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.ports.organizer_state_repository import (
    OrganizerStateRepositoryPort,
)

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


class OrganizerStateRepository(OrganizerStateRepositoryPort):
    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def get_ingested_ids(self, project_id: int) -> set[int]:
        with self._factory.connect() as conn:
            rows = conn.execute(
                "SELECT item_id FROM organizer_ingested_items WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return {row[0] for row in rows}

    def mark_ingested(self, project_id: int, item_id: int) -> None:
        with self._factory.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE"
                " INTO organizer_ingested_items"
                " (project_id, item_id) VALUES (?, ?)",
                (project_id, item_id),
            )
