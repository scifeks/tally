"""Unit tests for finding_vector_id."""

from __future__ import annotations

from application.rag.vector_doc_ids import finding_vector_id


class TestFindingVectorId:
    def test_returns_colon_joined_fingerprint_and_profile(self) -> None:
        assert finding_vector_id("fp1", "main") == "fp1:main"

    def test_empty_fingerprint_still_produces_stable_id(self) -> None:
        assert finding_vector_id("", "main") == ":main"

    def test_empty_profile_still_produces_stable_id(self) -> None:
        assert finding_vector_id("fp1", "") == "fp1:"
