"""ChromaDBVectorIndex lifecycle, upsert, query, get, count, delete."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any

import pytest

from application.ports.embedding_provider import EmbeddingProvider
from application.ports.filters import Eq
from application.ports.vector_index import VectorIndexError
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex

pytestmark = pytest.mark.integration


_DIM = 8


class _DeterministicEmbedding(EmbeddingProvider):
    """Hash-based embedding so the same text always maps to the same vector.

    Avoids any network or model dependency while still letting ChromaDB's
    cosine-distance index operate on stable points.
    """

    def is_available(self) -> bool:
        return True

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        floats = struct.unpack(f"<{_DIM}f", digest[: _DIM * 4])
        return list(floats)


@pytest.fixture()
def index(tmp_path: Path) -> ChromaDBVectorIndex:
    return ChromaDBVectorIndex(
        chroma_path=tmp_path / "chroma",
        collection_name="test_findings",
        embedding_provider=_DeterministicEmbedding(),
        collection_metadata={"hnsw:space": "cosine"},
    )


class TestChromaDBVectorIndex:
    def test_upsert_and_count(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["alpha finding", "beta finding"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["a", "b"],
        )
        assert index.count() == 2

    def test_get_by_ids(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["doc one"],
            metadatas=[{"tool": "semgrep"}],
            ids=["x1"],
        )
        rows = index.get(ids=["x1"])
        assert len(rows) == 1
        assert rows[0]["id"] == "x1"
        assert rows[0]["document"] == "doc one"
        assert rows[0]["metadata"] == {"tool": "semgrep"}

    def test_get_returns_empty_for_unknown_id(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["only doc"],
            metadatas=[{"tool": "semgrep"}],
            ids=["only"],
        )
        rows = index.get(ids=["missing"])
        assert rows == []

    def test_query_returns_matches_with_distance(
        self, index: ChromaDBVectorIndex
    ) -> None:
        index.upsert(
            documents=["sql injection in login form", "open redirect on /go"],
            metadatas=[{"tool": "semgrep"}, {"tool": "zap"}],
            ids=["sqli", "redir"],
        )
        matches = index.query("sql injection in login form", n_results=2)
        assert len(matches) == 2
        ids = {m["id"] for m in matches}
        assert ids == {"sqli", "redir"}
        for match in matches:
            assert match["distance"] is not None

    def test_query_with_filter_restricts_results(
        self, index: ChromaDBVectorIndex
    ) -> None:
        index.upsert(
            documents=["one", "two"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["s1", "g1"],
        )
        matches = index.query("one", n_results=5, filter=Eq("tool", "semgrep"))
        assert [m["id"] for m in matches] == ["s1"]

    def test_count_with_filter(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["a", "b", "c"],
            metadatas=[
                {"tool": "semgrep"},
                {"tool": "semgrep"},
                {"tool": "gitleaks"},
            ],
            ids=["a", "b", "c"],
        )
        assert index.count(Eq("tool", "semgrep")) == 2
        assert index.count(Eq("tool", "gitleaks")) == 1

    def test_delete_removes_ids(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["x", "y"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["x", "y"],
        )
        index.delete(["x"])
        assert index.count() == 1
        rows = index.get(ids=["x"])
        assert rows == []

    def test_delete_empty_list_is_noop(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["only"],
            metadatas=[{"tool": "semgrep"}],
            ids=["only"],
        )
        index.delete([])
        assert index.count() == 1

    def test_get_with_limit_and_offset(self, index: ChromaDBVectorIndex) -> None:
        index.upsert(
            documents=["a", "b", "c"],
            metadatas=[{"i": 1}, {"i": 2}, {"i": 3}],
            ids=["a", "b", "c"],
        )
        first = index.get(limit=2, offset=0)
        rest = index.get(limit=2, offset=2)
        assert len(first) == 2
        assert len(rest) == 1

    def test_upsert_same_id_overwrites_document_and_metadata(
        self, index: ChromaDBVectorIndex
    ) -> None:
        index.upsert(
            documents=["original text"],
            metadatas=[{"tool": "semgrep", "severity": "low"}],
            ids=["dup"],
        )
        index.upsert(
            documents=["replacement text"],
            metadatas=[{"tool": "semgrep", "severity": "high"}],
            ids=["dup"],
        )
        rows = index.get(ids=["dup"])
        assert len(rows) == 1
        assert rows[0]["document"] == "replacement text"
        assert rows[0]["metadata"] == {"tool": "semgrep", "severity": "high"}
        assert index.count() == 1

    def test_query_n_results_larger_than_collection(
        self, index: ChromaDBVectorIndex
    ) -> None:
        index.upsert(
            documents=["a", "b", "c"],
            metadatas=[{"tool": "x"}, {"tool": "x"}, {"tool": "x"}],
            ids=["a", "b", "c"],
        )
        matches = index.query("a", n_results=1000)
        assert len(matches) == 3

    def test_close_is_idempotent(self, index: ChromaDBVectorIndex) -> None:
        index.close()
        index.close()

    def test_construction_fails_when_provider_unavailable(self, tmp_path: Path) -> None:
        class _UnavailableProvider(EmbeddingProvider):
            def is_available(self) -> bool:
                return False

            def embed(self, text: str, **kwargs: Any) -> list[float]:
                raise NotImplementedError

        with pytest.raises(VectorIndexError):
            ChromaDBVectorIndex(
                chroma_path=tmp_path / "chroma",
                collection_name="findings",
                embedding_provider=_UnavailableProvider(),
            )
