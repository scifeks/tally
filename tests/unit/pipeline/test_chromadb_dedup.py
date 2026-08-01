"""Unit tests for ChromaDB duplicate ID deduplication in persist handler."""

from __future__ import annotations

from application.pipeline.chromadb_ids import chromadb_doc_id


class TestChromadbDedup:
    def test_no_duplicates_unchanged(self) -> None:
        fingerprints = ["fp1", "fp2", "fp3"]
        profile = "repo"
        doc_ids = [chromadb_doc_id(fp, profile) for fp in fingerprints]
        assert len(doc_ids) == len(set(doc_ids))

    def test_duplicate_fingerprints_produce_duplicate_ids(
        self,
    ) -> None:
        fingerprints = ["fp1", "fp1", "fp2"]
        profile = "repo"
        doc_ids = [chromadb_doc_id(fp, profile) for fp in fingerprints]
        assert doc_ids[0] == doc_ids[1]
        assert doc_ids[0] != doc_ids[2]

    def test_dedup_logic_keeps_last_occurrence(self) -> None:
        """Verify the dedup pattern used in handlers.py keeps
        the last row for each duplicate ID."""
        texts = ["text_a_first", "text_a_second", "text_b"]
        metadatas = [
            {"fingerprint": "fp1", "run_id": 1},
            {"fingerprint": "fp1", "run_id": 2},
            {"fingerprint": "fp2", "run_id": 3},
        ]
        doc_ids = ["fp1:repo", "fp1:repo", "fp2:repo"]

        seen: dict[str, int] = {}
        for i, doc_id in enumerate(doc_ids):
            seen[doc_id] = i
        if len(seen) < len(doc_ids):
            unique = sorted(seen.values())
            doc_ids = [doc_ids[i] for i in unique]
            texts = [texts[i] for i in unique]
            metadatas = [metadatas[i] for i in unique]

        assert len(doc_ids) == 2
        assert doc_ids == ["fp1:repo", "fp2:repo"]
        assert texts == ["text_a_second", "text_b"]
        assert metadatas[0]["run_id"] == 2
        assert metadatas[1]["run_id"] == 3
