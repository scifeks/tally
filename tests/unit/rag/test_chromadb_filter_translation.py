"""Pin the Filter AST -> ChromaDB DSL translation."""

from __future__ import annotations

import pytest

from application.ports.filters import And, Contains, Eq, Or
from application.ports.vector_index import VectorIndexError
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex


class TestTranslateClause:
    def test_eq_string(self) -> None:
        assert ChromaDBVectorIndex._translate_clause(Eq("tool", "semgrep")) == {
            "tool": {"$eq": "semgrep"}
        }

    def test_eq_int(self) -> None:
        assert ChromaDBVectorIndex._translate_clause(Eq("port", 80)) == {
            "port": {"$eq": 80}
        }

    def test_eq_bool(self) -> None:
        assert ChromaDBVectorIndex._translate_clause(Eq("type_secret", True)) == {
            "type_secret": {"$eq": True}
        }

    def test_contains(self) -> None:
        assert ChromaDBVectorIndex._translate_clause(Contains("file_path", "auth")) == {
            "file_path": {"$contains": "auth"}
        }

    def test_and(self) -> None:
        clause = And(clauses=(Eq("tool", "semgrep"), Eq("severity", "high")))
        assert ChromaDBVectorIndex._translate_clause(clause) == {
            "$and": [
                {"tool": {"$eq": "semgrep"}},
                {"severity": {"$eq": "high"}},
            ]
        }

    def test_or(self) -> None:
        clause = Or(clauses=(Eq("severity", "high"), Eq("severity", "critical")))
        assert ChromaDBVectorIndex._translate_clause(clause) == {
            "$or": [
                {"severity": {"$eq": "high"}},
                {"severity": {"$eq": "critical"}},
            ]
        }

    def test_nested_and_or(self) -> None:
        clause = And(
            clauses=(
                Eq("tool", "semgrep"),
                Or(
                    clauses=(
                        Eq("severity", "high"),
                        Eq("severity", "critical"),
                    )
                ),
            )
        )
        assert ChromaDBVectorIndex._translate_clause(clause) == {
            "$and": [
                {"tool": {"$eq": "semgrep"}},
                {
                    "$or": [
                        {"severity": {"$eq": "high"}},
                        {"severity": {"$eq": "critical"}},
                    ]
                },
            ]
        }

    def test_unknown_clause_raises(self) -> None:
        class _BogusFilter:
            pass

        with pytest.raises(VectorIndexError):
            ChromaDBVectorIndex._translate_clause(_BogusFilter())  # type: ignore[arg-type]

    def test_translate_filter_returns_none_for_none(self) -> None:
        assert ChromaDBVectorIndex._translate_filter(None) is None
