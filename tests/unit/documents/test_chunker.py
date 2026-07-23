"""Unit tests for text chunker."""

from __future__ import annotations

import pytest

from infrastructure.documents.chunker import chunk_text


class TestChunkText:
    def test_short_text_returns_single_chunk(self) -> None:
        text = "Hello world."
        chunks = chunk_text(text, chunk_size=2000, overlap=400)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_returns_empty_list(self) -> None:
        assert chunk_text("", chunk_size=2000, overlap=400) == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert chunk_text("   \n\n  ", chunk_size=2000, overlap=400) == []

    def test_long_text_produces_overlapping_chunks(self) -> None:
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        assert len(chunks) > 1
        for i in range(1, len(chunks)):
            # Verify overlap region matches between consecutive chunks
            overlap_size = min(50, len(chunks[i - 1]))
            prev_tail = chunks[i - 1][-overlap_size:]
            curr_start = chunks[i][:overlap_size]
            assert prev_tail == curr_start

    def test_chunks_do_not_exceed_size(self) -> None:
        text = "word " * 1000
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        for c in chunks:
            assert len(c) <= 200 + 50

    @pytest.mark.parametrize(
        "chunk_size,overlap",
        [(100, 20), (500, 100), (2000, 400)],
    )
    def test_all_content_preserved(self, chunk_size: int, overlap: int) -> None:
        words = [f"word{i}" for i in range(200)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        combined = " ".join(chunks)
        for w in words:
            assert w in combined
