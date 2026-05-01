"""Filter AST -> ChromaDB DSL round-trip against a real collection."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any

import pytest

from application.ports.embedding_provider import EmbeddingProvider
from application.ports.filters import And, Eq, Or
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex

pytestmark = pytest.mark.integration


_DIM = 8


class _DeterministicEmbedding(EmbeddingProvider):
    def is_available(self) -> bool:
        return True

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return list(struct.unpack(f"<{_DIM}f", digest[: _DIM * 4]))


@pytest.fixture()
def index(tmp_path: Path) -> ChromaDBVectorIndex:
    idx = ChromaDBVectorIndex(
        chroma_path=tmp_path / "chroma",
        collection_name="filter_round_trip",
        embedding_provider=_DeterministicEmbedding(),
    )
    idx.upsert(
        documents=[
            "sql injection in login",
            "open redirect on /go",
            "secret key committed",
            "xss in profile bio",
        ],
        metadatas=[
            {"tool": "semgrep", "severity": "high", "title": "SQL injection"},
            {"tool": "zap", "severity": "medium", "title": "Open redirect"},
            {"tool": "gitleaks", "severity": "high", "title": "Leaked key"},
            {"tool": "semgrep", "severity": "medium", "title": "XSS attack"},
        ],
        ids=["sqli", "redir", "leak", "xss"],
    )
    return idx


class TestChromaDBAdapterFilters:
    def test_eq_filter(self, index: ChromaDBVectorIndex) -> None:
        rows = index.get(filter=Eq("tool", "semgrep"))
        assert {r["id"] for r in rows} == {"sqli", "xss"}

    def test_and_filter(self, index: ChromaDBVectorIndex) -> None:
        rows = index.get(
            filter=And(
                clauses=(
                    Eq("tool", "semgrep"),
                    Eq("severity", "high"),
                )
            )
        )
        assert [r["id"] for r in rows] == ["sqli"]

    def test_or_filter(self, index: ChromaDBVectorIndex) -> None:
        rows = index.get(
            filter=Or(
                clauses=(
                    Eq("tool", "gitleaks"),
                    Eq("tool", "zap"),
                )
            )
        )
        assert {r["id"] for r in rows} == {"leak", "redir"}

    def test_nested_and_or(self, index: ChromaDBVectorIndex) -> None:
        rows = index.get(
            filter=And(
                clauses=(
                    Eq("severity", "high"),
                    Or(
                        clauses=(
                            Eq("tool", "semgrep"),
                            Eq("tool", "gitleaks"),
                        )
                    ),
                )
            )
        )
        assert {r["id"] for r in rows} == {"sqli", "leak"}

    def test_count_with_and_filter(self, index: ChromaDBVectorIndex) -> None:
        assert (
            index.count(
                And(
                    clauses=(
                        Eq("tool", "semgrep"),
                        Eq("severity", "medium"),
                    )
                )
            )
            == 1
        )

    def test_query_with_and_filter(self, index: ChromaDBVectorIndex) -> None:
        matches = index.query(
            "sql injection",
            n_results=5,
            filter=And(
                clauses=(
                    Eq("tool", "semgrep"),
                    Eq("severity", "high"),
                )
            ),
        )
        assert [m["id"] for m in matches] == ["sqli"]
