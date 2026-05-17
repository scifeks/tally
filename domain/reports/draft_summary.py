"""Domain value object for draft section summaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DraftSectionSummary:
    section: str
    status: str
    generated_at: str | None
    reviewed_at: str | None
    uploaded_filename: str | None
    word_count: int | None
    preview: str | None
    error: str | None
