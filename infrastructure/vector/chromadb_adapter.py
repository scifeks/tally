"""ChromaDB-backed implementation of the VectorIndex port."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import chromadb
    from chromadb.api import ClientAPI
    from chromadb.api.types import Documents, Embeddings

from application.ports.embedding_provider import EmbeddingProvider
from application.ports.filters import And, Contains, Eq, Filter, Or
from application.ports.vector_index import (
    VectorIndex,
    VectorIndexError,
    VectorMatch,
)

logger = logging.getLogger(__name__)


class _ProviderEmbeddingFn:
    """ChromaDB EmbeddingFunction wrapping an EmbeddingProvider."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        return [self._provider.embed(t) for t in input]  # type: ignore[return-value]

    def embed_query(self, input: Documents) -> Embeddings:  # noqa: A002
        return [self._provider.embed(t) for t in input]  # type: ignore[return-value]

    def name(self) -> str:
        return "default"

    def is_legacy(self) -> bool:
        # No get_config / default_space / supported_spaces; declaring legacy
        # silences the ChromaDB >=1.5 DeprecationWarning.
        return True


class ChromaDBVectorIndex(VectorIndex):
    """Project-scoped ChromaDB-backed VectorIndex."""

    def __init__(
        self,
        chroma_path: Path,
        collection_name: str,
        embedding_provider: EmbeddingProvider,
        collection_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        import chromadb
        from chromadb.api.types import Embeddable, EmbeddingFunction

        self._chroma_path = chroma_path
        self._collection_name = collection_name
        self._collection_metadata: dict[str, Any] = dict(
            collection_metadata or {"hnsw:space": "cosine"}
        )

        try:
            self._client: ClientAPI = chromadb.PersistentClient(path=str(chroma_path))
        except Exception as exc:
            raise VectorIndexError(
                f"ChromaDB client init failed at {chroma_path}: {exc}"
            ) from exc

        if not embedding_provider.is_available():
            raise VectorIndexError(
                "Embedding provider is not available. "
                "Please start it with: ollama serve"
            )

        embedding_fn = cast(
            EmbeddingFunction[Embeddable],
            _ProviderEmbeddingFn(embedding_provider),
        )

        try:
            self._collection: chromadb.Collection = (
                self._client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=embedding_fn,
                    metadata=self._collection_metadata,
                )
            )
        except Exception as exc:
            raise VectorIndexError(
                f"Could not open ChromaDB collection {collection_name!r}: {exc}"
            ) from exc

        logger.debug(
            "ChromaDBVectorIndex ready: collection=%s path=%s",
            collection_name,
            chroma_path,
        )

    def upsert(
        self,
        documents: list[str],
        metadatas: list[Mapping[str, Any]],
        ids: list[str],
    ) -> None:
        try:
            self._collection.upsert(
                documents=documents,
                metadatas=[dict(m) for m in metadatas],  # type: ignore[arg-type]
                ids=ids,
            )
        except Exception as exc:
            raise VectorIndexError(f"upsert failed: {exc}") from exc

    def query(
        self,
        text: str,
        *,
        n_results: int,
        filter: Filter | None = None,
    ) -> list[VectorMatch]:
        kwargs: dict[str, Any] = {
            "query_texts": [text],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        where = self._translate_filter(filter)
        if where is not None:
            kwargs["where"] = where
        try:
            raw = self._collection.query(**kwargs)
        except Exception as exc:
            raise VectorIndexError(f"query failed: {exc}") from exc
        return self._unpack_query_result(raw)

    def get(
        self,
        *,
        filter: Filter | None = None,
        ids: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[VectorMatch]:
        kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if ids is not None:
            kwargs["ids"] = ids
        where = self._translate_filter(filter)
        if where is not None:
            kwargs["where"] = where
        if limit is not None:
            kwargs["limit"] = limit
        if offset is not None:
            kwargs["offset"] = offset
        try:
            raw = self._collection.get(**kwargs)
        except Exception as exc:
            raise VectorIndexError(f"get failed: {exc}") from exc
        return self._unpack_get_result(raw)

    def count(self, filter: Filter | None = None) -> int:
        if filter is None:
            try:
                return self._collection.count()
            except Exception as exc:
                raise VectorIndexError(f"count failed: {exc}") from exc

        kwargs: dict[str, Any] = {"include": []}
        where = self._translate_filter(filter)
        if where is not None:
            kwargs["where"] = where
        try:
            raw = self._collection.get(**kwargs)
            return len(raw.get("ids") or [])
        except Exception as exc:
            raise VectorIndexError(f"count failed: {exc}") from exc

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            self._collection.delete(ids=ids)
        except Exception as exc:
            raise VectorIndexError(f"delete failed: {exc}") from exc

    def close(self) -> None:
        if hasattr(self._client, "close"):
            try:
                self._client.close()  # type: ignore[union-attr]
            except Exception:
                pass

    @classmethod
    def _translate_filter(cls, filter: Filter | None) -> dict[str, Any] | None:
        if filter is None:
            return None
        return cls._translate_clause(filter)

    @classmethod
    def _translate_clause(cls, clause: Filter) -> dict[str, Any]:
        if isinstance(clause, Eq):
            return {clause.field: {"$eq": clause.value}}
        if isinstance(clause, Contains):
            return {clause.field: {"$contains": clause.substring}}
        if isinstance(clause, And):
            return {"$and": [cls._translate_clause(c) for c in clause.clauses]}
        if isinstance(clause, Or):
            return {"$or": [cls._translate_clause(c) for c in clause.clauses]}
        raise VectorIndexError(f"Unsupported filter clause: {clause!r}")

    @staticmethod
    def _unpack_query_result(raw: Mapping[str, Any]) -> list[VectorMatch]:
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        matches: list[VectorMatch] = []
        for i, doc_id in enumerate(ids):
            matches.append(
                VectorMatch(
                    id=doc_id,
                    document=documents[i] if i < len(documents) else None,
                    metadata=metadatas[i] if i < len(metadatas) else None,
                    distance=distances[i] if i < len(distances) else None,
                )
            )
        return matches

    @staticmethod
    def _unpack_get_result(raw: Mapping[str, Any]) -> list[VectorMatch]:
        ids = raw.get("ids") or []
        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []
        matches: list[VectorMatch] = []
        for i, doc_id in enumerate(ids):
            matches.append(
                VectorMatch(
                    id=doc_id,
                    document=documents[i] if i < len(documents) else None,
                    metadata=metadatas[i] if i < len(metadatas) else None,
                    distance=None,
                )
            )
        return matches
