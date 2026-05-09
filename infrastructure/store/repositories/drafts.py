"""CRUD for the per-project ``drafts`` table."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from application.ports.draft_repository import DraftRepositoryPort
from domain.reports.entry import DraftRow

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


DRAFT_STATUSES = ("generating", "draft", "reviewed", "failed")


class DraftRepository(DraftRepositoryPort):
    """CRUD for the project-scoped ``drafts`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # Queries

    def get(self, section: str) -> DraftRow | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM drafts WHERE section = ?", (section,)
            ).fetchone()
        return _row_to_draft(row) if row else None

    def list_all(self) -> list[DraftRow]:
        with self._factory.connect() as conn:
            rows = conn.execute("SELECT * FROM drafts ORDER BY section").fetchall()
        return [_row_to_draft(r) for r in rows]

    # Lifecycle mutations

    def upsert_generating(self, section: str) -> None:
        """Insert or update *section* to ``generating``, clearing timestamps."""
        with self._factory.connect() as conn:
            conn.execute(
                "INSERT INTO drafts (section, status)"
                " VALUES (?, 'generating')"
                " ON CONFLICT(section) DO UPDATE SET"
                "   status = 'generating',"
                "   original_filename = NULL,"
                "   generated_at = NULL,"
                "   reviewed_at = NULL,"
                "   error = NULL",
                (section,),
            )

    def mark_drafted(self, section: str, generated_at: str | None = None) -> None:
        """Set *section* to ``draft`` after successful LLM generation."""
        ts = generated_at or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE drafts"
                " SET status = 'draft', generated_at = ?,"
                "     original_filename = NULL, reviewed_at = NULL,"
                "     error = NULL"
                " WHERE section = ?",
                (ts, section),
            )

    def mark_reviewed(
        self,
        section: str,
        original_filename: str,
        reviewed_at: str | None = None,
    ) -> None:
        """Set *section* to ``reviewed`` after a user upload (upsert)."""
        ts = reviewed_at or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "INSERT INTO drafts"
                " (section, status, original_filename, reviewed_at)"
                " VALUES (?, 'reviewed', ?, ?)"
                " ON CONFLICT(section) DO UPDATE SET"
                "   status = 'reviewed',"
                "   original_filename = excluded.original_filename,"
                "   reviewed_at = excluded.reviewed_at,"
                "   error = NULL",
                (section, original_filename, ts),
            )

    def mark_failed(self, section: str, error: str) -> None:
        """Persist failure for *section* with a user-facing *error* string."""
        with self._factory.connect() as conn:
            conn.execute(
                "INSERT INTO drafts (section, status, error)"
                " VALUES (?, 'failed', ?)"
                " ON CONFLICT(section) DO UPDATE SET"
                "   status = 'failed',"
                "   error = excluded.error,"
                "   original_filename = NULL,"
                "   generated_at = NULL,"
                "   reviewed_at = NULL",
                (section, error),
            )

    def delete(self, section: str) -> None:
        with self._factory.connect() as conn:
            conn.execute("DELETE FROM drafts WHERE section = ?", (section,))


def _row_to_draft(row: Any) -> DraftRow:
    return DraftRow(
        section=row["section"],
        status=row["status"],
        original_filename=row["original_filename"],
        generated_at=row["generated_at"],
        reviewed_at=row["reviewed_at"],
        error=row["error"],
    )
