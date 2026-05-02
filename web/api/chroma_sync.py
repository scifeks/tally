"""Best-effort ChromaDB sync for analyst PATCH edits."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.rag.ingestor import ToolHandlerFactory
from application.rag.knowledge_base import FindingKnowledgeBase

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort

logger = logging.getLogger(__name__)


def sync_finding_to_chroma(
    finding_id: int,
    knowledge_base: FindingKnowledgeBase | None,
    finding_repo: FindingRepositoryPort,
) -> None:
    """Best-effort ChromaDB upsert after a SQLite analyst PATCH.

    Fetches the updated row, renders text via ``ToolHandler.render()``,
    and upserts via the knowledge base. Never raises; all exceptions are
    caught and logged as warnings.
    """
    try:
        if knowledge_base is None:
            logger.warning("Chroma sync: knowledge base not available; skipping")
            return

        rows = finding_repo.get_by_ids([finding_id])
        if not rows:
            logger.warning(
                "Chroma sync: finding id=%s not found in SQLite (skipping)",
                finding_id,
            )
            return

        row = rows[0]
        handler = ToolHandlerFactory.load(row["tool"])
        if handler is None:
            logger.warning(
                "Chroma sync: no handler for tool=%s (finding id=%s) (skipping)",
                row["tool"],
                finding_id,
            )
            return

        text = handler.render(row)
        metadata = {"tool": row["tool"], "profile": row["profile"]}
        knowledge_base.add_findings(
            documents=[text],
            metadatas=[metadata],
            ids=[str(row["id"])],
        )
    except Exception as exc:
        logger.warning(
            "Chroma sync: unexpected error for finding id=%s: %s",
            finding_id,
            exc,
        )
