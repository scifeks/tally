"""Tests for chromadb_ids helper function."""

from application.pipeline.chromadb_ids import chromadb_doc_id


class TestChromadbDocId:
    """Test chromadb_doc_id function."""

    def test_combines_fingerprint_and_profile(self) -> None:
        """Verify fingerprint and profile are combined with colon separator."""
        result = chromadb_doc_id("abc123", "my-repo")
        assert result == "abc123:my-repo"

    def test_handles_empty_profile(self) -> None:
        """Verify empty profile is preserved in the doc ID."""
        result = chromadb_doc_id("abc123", "")
        assert result == "abc123:"
