"""FindingIndexer: coordinates writing finding rows into the vector index."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from application.ports.vector_index import VectorIndexError
from application.rag.ingestor import ToolHandlerFactory
from application.rag.vector_doc_ids import finding_vector_id
from domain.findings.normalization import prepare_row_for_render

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from application.rag.knowledge_base import FindingKnowledgeBase


logger = logging.getLogger(__name__)


class FindingIndexer:
    """Coordinates writing finding rows into the vector index.

    Reads rows from the relational finding repository, groups them by
    tool + profile, renders per-row text via each tool's ToolHandler,
    dedupes by stable document id, and upserts through the
    FindingKnowledgeBase (which delegates to the VectorIndex port).
    """

    def __init__(self, finding_repo: FindingRepositoryPort) -> None:
        self._finding_repo = finding_repo

    def index_findings(
        self,
        knowledge_base: FindingKnowledgeBase,
        ids: list[int],
        caller_label: str = "FindingIndexer",
    ) -> None:
        if not ids:
            return
        rows = self._finding_repo.get_by_ids(ids)
        grouped: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            grouped[(row["tool"], row["profile"])].append(row)
        for (tool, profile), group_rows in grouped.items():
            handler = ToolHandlerFactory.load(tool)
            if handler is None:
                continue
            texts = [
                f"Repository: {profile} | {handler.render(prepare_row_for_render(row))}"
                for row in group_rows
            ]
            metadatas: list[Mapping[str, Any]] = [
                {
                    "tool": tool,
                    "profile": profile,
                    "run_id": row.get("run_id", 0),
                    "severity": row.get("severity", ""),
                    "segment": row.get("segment", ""),
                    "status": row.get("status", "active"),
                    "fingerprint": row.get("fingerprint", ""),
                }
                for row in group_rows
            ]
            doc_ids = [
                finding_vector_id(row.get("fingerprint", ""), profile)
                for row in group_rows
            ]
            seen: dict[str, int] = {}
            for i, doc_id in enumerate(doc_ids):
                seen[doc_id] = i
            if len(seen) < len(doc_ids):
                unique = sorted(seen.values())
                doc_ids = [doc_ids[i] for i in unique]
                texts = [texts[i] for i in unique]
                metadatas = [metadatas[i] for i in unique]
            try:
                knowledge_base.add_findings(
                    documents=texts,
                    metadatas=metadatas,
                    ids=doc_ids,
                )
            except VectorIndexError as exc:
                logger.error(
                    "%s: vector index write failed for tool=%s: %s",
                    caller_label,
                    tool,
                    exc,
                )

    def remove_findings(
        self,
        knowledge_base: FindingKnowledgeBase,
        rows: Sequence[Mapping[str, Any]],
        caller_label: str = "FindingIndexer",
    ) -> None:
        if not rows:
            return
        doc_ids = [
            finding_vector_id(
                str(row.get("fingerprint", "")),
                str(row.get("profile", "")),
            )
            for row in rows
        ]
        try:
            knowledge_base.remove_findings_by_id(doc_ids)
        except VectorIndexError as exc:
            logger.error(
                "%s: vector index remove failed: %s",
                caller_label,
                exc,
            )
