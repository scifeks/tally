"""Application service for finding-document storage and retrieval."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.ports.filters import And, Eq, Filter
from application.ports.llm_provider import LLMProvider
from application.ports.vector_index import VectorIndex, VectorMatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeBaseStats:
    total_documents: int
    by_tool: Mapping[str, int]
    by_severity: Mapping[str, int]
    last_updated: str | None


class FindingKnowledgeBase:
    """Project-scoped service over a VectorIndex of security findings."""

    def __init__(
        self,
        vector_index: VectorIndex,
        chat_provider: LLMProvider,
        project_name: str,
        base_path: Path,
    ) -> None:
        if not project_name:
            raise ValueError("project_name must not be empty")

        self._index = vector_index
        self._chat_provider = chat_provider
        self._project_name = project_name
        self._base_path = base_path

    @property
    def chat_provider(self) -> LLMProvider:
        return self._chat_provider

    @property
    def base_path(self) -> Path:
        return self._base_path

    @property
    def project_name(self) -> str:
        return self._project_name

    def add_findings(
        self,
        documents: list[str],
        metadatas: list[Mapping[str, Any]],
        ids: list[str],
    ) -> None:
        self._index.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def delete_findings(
        self,
        tool: str | None = None,
        profile: str | None = None,
    ) -> int:
        """Delete findings filtered by tool and/or profile.

        ``tool=None, profile=None`` deletes everything. ``profile`` without
        ``tool`` raises ValueError.
        """
        if profile is not None and tool is None:
            raise ValueError("--profile requires --tool to be specified")

        filter_clause: Filter | None
        if tool is not None and profile is not None:
            filter_clause = And(clauses=(Eq("tool", tool), Eq("profile", profile)))
        elif tool is not None:
            filter_clause = Eq("tool", tool)
        else:
            filter_clause = None

        try:
            matches = self._index.get(filter=filter_clause)
            ids = [m["id"] for m in matches]
            if ids:
                self._index.delete(ids)
            return len(ids)
        except Exception as exc:
            logger.warning(
                "delete_findings failed (tool=%s profile=%s): %s",
                tool,
                profile,
                exc,
            )
            return 0

    def find_relevant(
        self,
        text: str,
        n_results: int,
        filter: Filter | None = None,
    ) -> list[VectorMatch]:
        return self._index.query(text, n_results=n_results, filter=filter)

    def find_by_filter(
        self,
        filter: Filter | None,
        limit: int,
        offset: int,
    ) -> list[VectorMatch]:
        return self._index.get(filter=filter, limit=limit, offset=offset)

    def count(self, filter: Filter | None = None) -> int:
        return self._index.count(filter)

    def get_finding(self, finding_id: str) -> VectorMatch | None:
        matches = self._index.get(ids=[finding_id])
        if not matches:
            return None
        return matches[0]

    def compute_stats(self) -> KnowledgeBaseStats:
        total = self._index.count()
        if total == 0:
            return KnowledgeBaseStats(
                total_documents=0,
                by_tool={},
                by_severity={},
                last_updated=None,
            )

        by_tool: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        latest_ts: str | None = None

        try:
            for match in self._index.get():
                meta = match.get("metadata") or {}
                tool = str(meta.get("tool", "unknown"))
                by_tool[tool] = by_tool.get(tool, 0) + 1

                severity = meta.get("severity")
                if severity:
                    by_severity[str(severity)] = by_severity.get(str(severity), 0) + 1

                ts = meta.get("timestamp")
                if ts and (latest_ts is None or str(ts) > latest_ts):
                    latest_ts = str(ts)
        except Exception as exc:
            logger.warning("compute_stats metadata fetch failed: %s", exc)

        return KnowledgeBaseStats(
            total_documents=total,
            by_tool=by_tool,
            by_severity=by_severity,
            last_updated=latest_ts,
        )

    def close(self) -> None:
        self._index.close()
