"""Unit tests for web segment batch sizing."""

from __future__ import annotations

from application.triage.batching import (
    MAX_FINDINGS_PER_BATCH,
    WEB_FINDINGS_PER_BATCH,
    batch_size_for_segment,
    compute_batches,
)


class TestBatchSizeForSegment:
    def test_web_returns_one(self) -> None:
        assert batch_size_for_segment("web") == 1

    def test_sast_returns_default(self) -> None:
        assert batch_size_for_segment("sast") == MAX_FINDINGS_PER_BATCH

    def test_unknown_segment_returns_default(self) -> None:
        assert batch_size_for_segment("secrets") == MAX_FINDINGS_PER_BATCH

    def test_custom_default_passed_through(self) -> None:
        assert batch_size_for_segment("sast", default=8) == 8

    def test_web_ignores_custom_default(self) -> None:
        assert batch_size_for_segment("web", default=8) == 1

    def test_web_constant_is_one(self) -> None:
        assert WEB_FINDINGS_PER_BATCH == 1


class TestComputeBatchesWebSize:
    def test_size_one_produces_single_finding_batches(
        self,
    ) -> None:
        findings = [
            {"id": 1, "url": "/a"},
            {"id": 2, "url": "/b"},
            {"id": 3, "url": "/c"},
        ]
        batches = compute_batches(findings, max_findings_per_batch=1)

        assert len(batches) == 3
        assert all(len(b) == 1 for b in batches)
        ids = [b[0]["id"] for b in batches]
        assert ids == [1, 2, 3]
