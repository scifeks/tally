"""Unit tests for DocumentStore."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.rag.document_store import DocumentStore


class TestDocumentStore:
    """Tests for the DocumentStore application service."""

    def _make_store(self) -> tuple[DocumentStore, MagicMock]:
        """Create a DocumentStore with a mocked VectorIndex."""
        mock_index = MagicMock()
        store = DocumentStore(mock_index)
        return store, mock_index

    def test_add_chunks_calls_upsert_with_correct_args(self) -> None:
        """Verify add_chunks calls upsert with proper structure."""
        store, mock_index = self._make_store()

        chunks = ["chunk1", "chunk2"]
        store.add_chunks("test.md", chunks)

        mock_index.upsert.assert_called_once()
        call_args = mock_index.upsert.call_args
        assert call_args is not None

        documents = call_args[1]["documents"]
        metadatas = call_args[1]["metadatas"]
        ids = call_args[1]["ids"]

        assert documents == ["chunk1", "chunk2"]
        assert len(metadatas) == 2
        assert len(ids) == 2

        # Check metadata structure
        for i, meta in enumerate(metadatas):
            assert meta["source_type"] == "user_doc"
            assert meta["source_file"] == "test.md"
            assert meta["chunk_index"] == i
            assert meta["total_chunks"] == 2

        # Check ID format
        assert ids[0] == "doc:test.md:0"
        assert ids[1] == "doc:test.md:1"

    def test_add_chunks_returns_count(self) -> None:
        """Verify add_chunks returns the number of chunks added."""
        store, mock_index = self._make_store()

        count = store.add_chunks("test.md", ["a", "b", "c"])
        assert count == 3

    def test_add_empty_chunks_returns_zero(self) -> None:
        """Verify empty chunk list returns 0 and does not call upsert."""
        store, mock_index = self._make_store()

        count = store.add_chunks("test.md", [])
        assert count == 0
        mock_index.upsert.assert_not_called()

    def test_remove_by_filename_deletes_matching_chunks(self) -> None:
        """Verify remove_by_filename deletes all chunks with matching file."""
        store, mock_index = self._make_store()

        # Mock get() to return matching documents
        mock_index.get.return_value = [
            {
                "id": "doc:test.md:0",
                "document": "chunk1",
                "metadata": {"source_file": "test.md"},
                "distance": 0.1,
            },
            {
                "id": "doc:test.md:1",
                "document": "chunk2",
                "metadata": {"source_file": "test.md"},
                "distance": 0.2,
            },
        ]

        count = store.remove_by_filename("test.md")

        assert count == 2
        mock_index.get.assert_called_once()
        mock_index.delete.assert_called_once_with(["doc:test.md:0", "doc:test.md:1"])

    def test_remove_by_filename_returns_zero_when_no_matches(self) -> None:
        """Verify remove_by_filename returns 0 and does not call delete."""
        store, mock_index = self._make_store()

        # Mock get() to return empty
        mock_index.get.return_value = []

        count = store.remove_by_filename("nonexistent.md")

        assert count == 0
        mock_index.delete.assert_not_called()

    def test_list_sources_aggregates_metadata(self) -> None:
        """Verify list_sources returns unique files with chunk counts."""
        store, mock_index = self._make_store()

        # Mock get() to return documents from different files
        mock_index.get.return_value = [
            {
                "id": "doc:file1.md:0",
                "document": "chunk",
                "metadata": {
                    "source_file": "file1.md",
                    "total_chunks": 2,
                },
                "distance": None,
            },
            {
                "id": "doc:file1.md:1",
                "document": "chunk",
                "metadata": {
                    "source_file": "file1.md",
                    "total_chunks": 2,
                },
                "distance": None,
            },
            {
                "id": "doc:file2.md:0",
                "document": "chunk",
                "metadata": {
                    "source_file": "file2.md",
                    "total_chunks": 3,
                },
                "distance": None,
            },
            {
                "id": "doc:file2.md:1",
                "document": "chunk",
                "metadata": {
                    "source_file": "file2.md",
                    "total_chunks": 3,
                },
                "distance": None,
            },
            {
                "id": "doc:file2.md:2",
                "document": "chunk",
                "metadata": {
                    "source_file": "file2.md",
                    "total_chunks": 3,
                },
                "distance": None,
            },
        ]

        sources = store.list_sources()

        assert len(sources) == 2
        assert sources[0] == {"name": "file1.md", "chunks": 2}
        assert sources[1] == {"name": "file2.md", "chunks": 3}

    def test_search_delegates_to_query(self) -> None:
        """Verify search calls query with correct arguments."""
        store, mock_index = self._make_store()

        expected_results = [
            {
                "id": "doc:test.md:0",
                "document": "matching chunk",
                "metadata": {"source_file": "test.md"},
                "distance": 0.1,
            }
        ]
        mock_index.query.return_value = expected_results

        results = store.search("search text", n_results=5)

        assert results == expected_results
        mock_index.query.assert_called_once_with("search text", n_results=5)

    def test_count_delegates_to_index(self) -> None:
        """Verify count delegates to the vector index."""
        store, mock_index = self._make_store()
        mock_index.count.return_value = 42

        count = store.count()

        assert count == 42
        mock_index.count.assert_called_once()

    def test_close_delegates_to_index(self) -> None:
        """Verify close delegates to the vector index."""
        store, mock_index = self._make_store()

        store.close()

        mock_index.close.assert_called_once()
