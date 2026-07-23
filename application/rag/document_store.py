"""Application service for user document storage and retrieval."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from application.ports.filters import Eq
from application.ports.vector_index import VectorIndex, VectorMatch

logger = logging.getLogger(__name__)


class DocumentStore:
    """Project-scoped service for user documents in a VectorIndex."""

    def __init__(self, vector_index: VectorIndex) -> None:
        self._index = vector_index

    def add_chunks(
        self,
        filename: str,
        chunks: list[str],
    ) -> int:
        """Store document chunks. Returns count stored."""
        if not chunks:
            return 0

        total = len(chunks)
        documents: list[str] = []
        metadatas: list[Mapping[str, Any]] = []
        ids: list[str] = []

        for i, chunk in enumerate(chunks):
            documents.append(chunk)
            metadatas.append(
                {
                    "source_type": "user_doc",
                    "source_file": filename,
                    "chunk_index": i,
                    "total_chunks": total,
                }
            )
            ids.append(f"doc:{filename}:{i}")

        self._index.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        return total

    def remove_by_filename(self, filename: str) -> int:
        """Remove all chunks for a given filename."""
        matches = self._index.get(
            filter=Eq("source_file", filename),
        )
        ids = [m["id"] for m in matches]
        if ids:
            self._index.delete(ids)
        return len(ids)

    def list_sources(self) -> list[dict[str, Any]]:
        """List unique source files with chunk counts."""
        matches = self._index.get()
        sources: dict[str, int] = {}
        for m in matches:
            meta = m.get("metadata") or {}
            name = str(meta.get("source_file", "unknown"))
            total = int(meta.get("total_chunks", 1))
            sources[name] = total
        return [
            {"name": name, "chunks": count} for name, count in sorted(sources.items())
        ]

    def search(
        self,
        text: str,
        n_results: int = 10,
    ) -> list[VectorMatch]:
        """Semantic search across stored documents."""
        return self._index.query(
            text,
            n_results=n_results,
        )

    def count(self) -> int:
        """Return total document count."""
        return self._index.count()

    def close(self) -> None:
        """Close the vector index."""
        self._index.close()
