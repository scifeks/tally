"""DraftRepository — manages the ``drafts`` table (Phase 7.5).

Each row tracks one draft section: generating → draft (LLM-written) or
reviewed (user-uploaded). The table lives in the per-project ``findings.db``
alongside the ``reports`` table; no ``project_id`` column is needed.

``not_generated`` is represented by the *absence* of a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


DRAFT_STATUSES = ("generating", "draft", "reviewed")


@dataclass(frozen=True)
class DraftRecord:
    section: str
    status: str
    original_filename: str | None
    generated_at: str | None
    reviewed_at: str | None


class DraftRepository:
    """CRUD for the project-scoped ``drafts`` table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, section: str) -> DraftRecord | None:
        with self._factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM drafts WHERE section = ?", (section,)
            ).fetchone()
        return _row_to_draft(row) if row else None

    def list_all(self) -> list[DraftRecord]:
        with self._factory.connect() as conn:
            rows = conn.execute("SELECT * FROM drafts ORDER BY section").fetchall()
        return [_row_to_draft(r) for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle mutations
    # ------------------------------------------------------------------

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
                "   reviewed_at = NULL",
                (section,),
            )

    def mark_drafted(self, section: str, generated_at: str | None = None) -> None:
        """Set *section* to ``draft`` after successful LLM generation."""
        ts = generated_at or datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "UPDATE drafts"
                " SET status = 'draft', generated_at = ?,"
                "     original_filename = NULL, reviewed_at = NULL"
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
                "   reviewed_at = excluded.reviewed_at",
                (section, original_filename, ts),
            )

    def restore(self, section: str, prior: DraftRecord | None) -> None:
        """Revert *section* to *prior* after a failed generation.

        If *prior* is ``None`` the row is deleted (section returns to
        ``not_generated``). Otherwise the row is reset to the prior fields.
        """
        if prior is None:
            with self._factory.connect() as conn:
                conn.execute("DELETE FROM drafts WHERE section = ?", (section,))
        else:
            with self._factory.connect() as conn:
                conn.execute(
                    "UPDATE drafts"
                    " SET status = ?,"
                    "     original_filename = ?,"
                    "     generated_at = ?,"
                    "     reviewed_at = ?"
                    " WHERE section = ?",
                    (
                        prior.status,
                        prior.original_filename,
                        prior.generated_at,
                        prior.reviewed_at,
                        section,
                    ),
                )

    def delete(self, section: str) -> None:
        with self._factory.connect() as conn:
            conn.execute("DELETE FROM drafts WHERE section = ?", (section,))


def _row_to_draft(row: Any) -> DraftRecord:
    return DraftRecord(
        section=row["section"],
        status=row["status"],
        original_filename=row["original_filename"],
        generated_at=row["generated_at"],
        reviewed_at=row["reviewed_at"],
    )
