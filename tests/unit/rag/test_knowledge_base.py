"""FindingKnowledgeBase compositions over a fake VectorIndex."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.ports.filters import And, Eq, Filter
from application.ports.vector_index import VectorMatch
from application.rag.knowledge_base import FindingKnowledgeBase, KnowledgeBaseStats


class _FakeVectorIndex:
    """Stub backing store with a list-of-rows model."""

    def __init__(self) -> None:
        self.rows: list[VectorMatch] = []
        self.upsert_calls: list[
            tuple[list[str], list[Mapping[str, Any]], list[str]]
        ] = []
        self.delete_calls: list[list[str]] = []
        self.close_calls = 0

    def upsert(
        self,
        documents: list[str],
        metadatas: list[Mapping[str, Any]],
        ids: list[str],
    ) -> None:
        self.upsert_calls.append((documents, metadatas, ids))
        for doc, meta, doc_id in zip(documents, metadatas, ids, strict=True):
            self.rows.append(
                VectorMatch(id=doc_id, document=doc, metadata=dict(meta), distance=None)
            )

    def query(
        self,
        text: str,
        *,
        n_results: int,
        filter: Filter | None = None,
    ) -> list[VectorMatch]:
        return self._filter_rows(filter)[:n_results]

    def get(
        self,
        *,
        filter: Filter | None = None,
        ids: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[VectorMatch]:
        if ids is not None:
            return [r for r in self.rows if r["id"] in ids]
        rows = self._filter_rows(filter)
        if offset is not None:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    def count(self, filter: Filter | None = None) -> int:
        return len(self._filter_rows(filter))

    def delete(self, ids: list[str]) -> None:
        self.delete_calls.append(list(ids))
        self.rows = [r for r in self.rows if r["id"] not in ids]

    def close(self) -> None:
        self.close_calls += 1

    def _filter_rows(self, clause: Filter | None) -> list[VectorMatch]:
        if clause is None:
            return list(self.rows)
        return [r for r in self.rows if self._matches(r, clause)]

    def _matches(self, row: VectorMatch, clause: Filter) -> bool:
        meta = row.get("metadata") or {}
        if isinstance(clause, Eq):
            return meta.get(clause.field) == clause.value
        if isinstance(clause, And):
            return all(self._matches(row, c) for c in clause.clauses)
        return False


@pytest.fixture()
def kb(tmp_path: Path) -> tuple[FindingKnowledgeBase, _FakeVectorIndex]:
    fake = _FakeVectorIndex()
    chat = MagicMock()
    base = FindingKnowledgeBase(
        vector_index=fake,  # type: ignore[arg-type]
        chat_provider=chat,
        project_name="testproj",
        base_path=tmp_path,
    )
    return base, fake


class TestFindingKnowledgeBase:
    def test_construction_rejects_empty_project_name(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            FindingKnowledgeBase(
                vector_index=_FakeVectorIndex(),  # type: ignore[arg-type]
                chat_provider=MagicMock(),
                project_name="",
                base_path=tmp_path,
            )

    def test_properties_expose_construction_state(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex], tmp_path: Path
    ) -> None:
        base, _ = kb
        assert base.project_name == "testproj"
        assert base.base_path == tmp_path

    def test_add_findings_delegates_to_upsert(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, fake = kb
        base.add_findings(
            documents=["a", "b"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["1", "2"],
        )
        assert fake.upsert_calls == [
            (["a", "b"], [{"tool": "semgrep"}, {"tool": "gitleaks"}], ["1", "2"])
        ]
        assert fake.count() == 2

    def test_delete_all_when_tool_and_profile_none(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, fake = kb
        base.add_findings(
            documents=["a", "b"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["1", "2"],
        )
        deleted = base.delete_findings()
        assert deleted == 2
        assert fake.count() == 0

    def test_delete_by_tool(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, fake = kb
        base.add_findings(
            documents=["a", "b", "c"],
            metadatas=[
                {"tool": "semgrep"},
                {"tool": "semgrep"},
                {"tool": "gitleaks"},
            ],
            ids=["1", "2", "3"],
        )
        deleted = base.delete_findings(tool="semgrep")
        assert deleted == 2
        assert {r["id"] for r in fake.rows} == {"3"}

    def test_delete_by_tool_and_profile(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, fake = kb
        base.add_findings(
            documents=["a", "b"],
            metadatas=[
                {"tool": "semgrep", "profile": "repo-x"},
                {"tool": "semgrep", "profile": "repo-y"},
            ],
            ids=["1", "2"],
        )
        deleted = base.delete_findings(tool="semgrep", profile="repo-x")
        assert deleted == 1
        assert [r["id"] for r in fake.rows] == ["2"]

    def test_delete_profile_without_tool_raises(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, _ = kb
        with pytest.raises(ValueError):
            base.delete_findings(profile="repo-x")

    def test_find_relevant_passes_through(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, fake = kb
        base.add_findings(
            documents=["alpha", "beta"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["1", "2"],
        )
        matches = base.find_relevant("alpha", n_results=1, filter=Eq("tool", "semgrep"))
        assert [m["id"] for m in matches] == ["1"]

    def test_find_by_filter_paginates(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, _ = kb
        base.add_findings(
            documents=["a", "b", "c"],
            metadatas=[
                {"tool": "semgrep"},
                {"tool": "semgrep"},
                {"tool": "gitleaks"},
            ],
            ids=["1", "2", "3"],
        )
        page = base.find_by_filter(Eq("tool", "semgrep"), limit=1, offset=1)
        assert [m["id"] for m in page] == ["2"]

    def test_count(self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]) -> None:
        base, _ = kb
        base.add_findings(
            documents=["a", "b"],
            metadatas=[{"tool": "semgrep"}, {"tool": "gitleaks"}],
            ids=["1", "2"],
        )
        assert base.count() == 2
        assert base.count(Eq("tool", "semgrep")) == 1

    def test_get_finding_returns_match(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, _ = kb
        base.add_findings(
            documents=["only"],
            metadatas=[{"tool": "semgrep"}],
            ids=["abc"],
        )
        match = base.get_finding("abc")
        assert match is not None
        assert match["id"] == "abc"

    def test_get_finding_returns_none_when_missing(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, _ = kb
        assert base.get_finding("missing") is None

    def test_compute_stats_empty(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, _ = kb
        stats = base.compute_stats()
        assert stats == KnowledgeBaseStats(
            total_documents=0, by_tool={}, by_severity={}, last_updated=None
        )

    def test_compute_stats_aggregates(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, _ = kb
        base.add_findings(
            documents=["a", "b", "c"],
            metadatas=[
                {"tool": "semgrep", "severity": "high", "timestamp": "2026-01-01"},
                {"tool": "semgrep", "severity": "low", "timestamp": "2026-02-01"},
                {"tool": "gitleaks", "timestamp": "2026-03-01"},
            ],
            ids=["1", "2", "3"],
        )
        stats = base.compute_stats()
        assert stats.total_documents == 3
        assert stats.by_tool == {"semgrep": 2, "gitleaks": 1}
        assert stats.by_severity == {"high": 1, "low": 1}
        assert stats.last_updated == "2026-03-01"

    def test_close_delegates_to_index(
        self, kb: tuple[FindingKnowledgeBase, _FakeVectorIndex]
    ) -> None:
        base, fake = kb
        base.close()
        assert fake.close_calls == 1
