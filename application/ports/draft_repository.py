"""Persistence port for the ``drafts`` table.

Concrete implementation lives at
``infrastructure.store.repositories.drafts.DraftRepository``. Read
methods return ``domain.reports.entry.DraftRow`` so the port boundary
stays free of infrastructure dataclasses.

A row's absence represents the ``not_generated`` state; ``get`` and
``list_all`` reflect the persisted rows only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.reports.entry import DraftRow


class DraftRepositoryPort(Protocol):
    def get(self, section: str) -> DraftRow | None: ...
    def list_all(self) -> list[DraftRow]: ...
    def upsert_generating(self, section: str) -> None: ...
    def mark_drafted(self, section: str, generated_at: str | None = None) -> None: ...
    def mark_reviewed(
        self,
        section: str,
        original_filename: str,
        reviewed_at: str | None = None,
    ) -> None: ...
    def restore(self, section: str, prior: DraftRow | None) -> None: ...
    def delete(self, section: str) -> None: ...
