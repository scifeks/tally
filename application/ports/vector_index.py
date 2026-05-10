"""VectorIndex port: storage-agnostic seam over a project's vector store."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict

from application.ports.filters import Filter


class VectorMatch(TypedDict):
    """Result row from a query or get on the vector store."""

    id: str
    document: str | None
    metadata: Mapping[str, Any] | None
    distance: float | None


class VectorIndexError(RuntimeError):
    """Raised by VectorIndex implementations when an operation fails."""


class VectorIndex(Protocol):
    """Project-scoped vector store seam."""

    def upsert(
        self,
        documents: list[str],
        metadatas: list[Mapping[str, Any]],
        ids: list[str],
    ) -> None: ...

    def query(
        self,
        text: str,
        *,
        n_results: int,
        filter: Filter | None = None,
    ) -> list[VectorMatch]: ...

    def get(
        self,
        *,
        filter: Filter | None = None,
        ids: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[VectorMatch]: ...

    def count(self, filter: Filter | None = None) -> int: ...

    def delete(self, ids: list[str]) -> None: ...

    def close(self) -> None: ...
