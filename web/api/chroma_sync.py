"""Best-effort ChromaDB sync for analyst PATCH edits."""

from __future__ import annotations

import logging

from application.rag.engine import RAGEngine
from application.rag.ingestor import ToolHandlerFactory
from infrastructure.store import FindingRepository

logger = logging.getLogger(__name__)


def sync_finding_to_chroma(
    finding_id: int,
    rag_engine: RAGEngine | None,
    finding_repo: FindingRepository,
) -> None:
    """Best-effort ChromaDB upsert after a SQLite analyst PATCH.

    Fetches the updated row by primary key, renders text via
    ``ToolHandler.render()``, and upserts to ChromaDB using
    ``str(findings.id)`` as the doc ID.  Never raises — all exceptions
    are caught and logged as warnings.  The PATCH endpoint returns 200
    regardless of this function's outcome.
    """
    try:
        if rag_engine is None:
            logger.warning("Chroma sync: RAGEngine not available — skipping")
            return

        rows = finding_repo.get_by_ids([finding_id])
        if not rows:
            logger.warning(
                "Chroma sync: finding id=%s not found in SQLite — skipping",
                finding_id,
            )
            return

        row = rows[0]
        handler = ToolHandlerFactory.load(row["tool"])
        if handler is None:
            logger.warning(
                "Chroma sync: no handler for tool=%s (finding id=%s) — skipping",
                row["tool"],
                finding_id,
            )
            return

        text = handler.render(row)
        metadata = {"tool": row["tool"], "profile": row["profile"]}
        rag_engine.add_documents(
            texts=[text],
            metadatas=[metadata],
            ids=[str(row["id"])],
        )
    except Exception as exc:
        logger.warning(
            "Chroma sync: unexpected error for finding id=%s: %s",
            finding_id,
            exc,
        )
