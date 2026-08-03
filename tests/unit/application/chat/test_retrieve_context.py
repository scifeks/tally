"""Unit tests for mode-aware chat context retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.chat.service import _retrieve_context
from application.ports.vector_index import VectorMatch


def _make_finding_match(
    doc_id: str,
    document: str,
    tool: str = "semgrep",
    profile: str = "myapp",
) -> VectorMatch:
    """Helper to construct a VectorMatch for a finding."""
    return {
        "id": doc_id,
        "document": document,
        "metadata": {"tool": tool, "profile": profile},
        "distance": 0.1,
    }


def _make_document_match(
    doc_id: str,
    document: str,
    source_file: str = "readme.md",
) -> VectorMatch:
    """Helper to construct a VectorMatch for a document."""
    return {
        "id": doc_id,
        "document": document,
        "metadata": {"source_file": source_file, "source_type": "user_doc"},
        "distance": 0.2,
    }


class TestRetrieveContext:
    """Tests for mode-aware context retrieval in chat service."""

    def test_mode_findings_with_results_returns_findings_section_only(
        self,
    ) -> None:
        """Mode 'findings' with results returns findings section only."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_finding_match(
                "f1",
                "SQL injection in login endpoint",
            ),
            _make_finding_match(
                "f2",
                "Cross-site scripting in search",
                tool="eslint",
                profile="webapp",
            ),
        ]

        context = _retrieve_context(
            mock_retriever,
            "security issues",
            mode="findings",
        )

        assert "Security Findings:" in context
        assert "SQL injection" in context
        assert "Cross-site scripting" in context
        assert "Project Documents:" not in context
        mock_retriever.search.assert_called_once()

    def test_mode_documents_with_store_returns_documents_section_only(
        self,
    ) -> None:
        """Mode 'documents' with store returns documents section only."""
        mock_retriever = MagicMock()
        mock_store = MagicMock()
        mock_store.search.return_value = [
            _make_document_match("d1", "Project architecture overview"),
            _make_document_match(
                "d2",
                "API endpoint documentation",
                source_file="api.md",
            ),
        ]

        context = _retrieve_context(
            mock_retriever,
            "how to use this",
            document_store=mock_store,
            mode="documents",
        )

        assert "Project Documents:" in context
        assert "architecture overview" in context
        assert "API endpoint" in context
        assert "Security Findings:" not in context
        mock_retriever.search.assert_not_called()
        mock_store.search.assert_called_once()

    def test_mode_all_with_both_sources_returns_both_sections(
        self,
    ) -> None:
        """Mode 'all' with both sources returns both sections."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_finding_match("f1", "XSS vulnerability found"),
        ]
        mock_store = MagicMock()
        mock_store.search.return_value = [
            _make_document_match("d1", "Security guidelines"),
        ]

        context = _retrieve_context(
            mock_retriever,
            "vulnerabilities and best practices",
            document_store=mock_store,
            mode="all",
        )

        assert "Security Findings:" in context
        assert "XSS vulnerability" in context
        assert "Project Documents:" in context
        assert "Security guidelines" in context
        lines = context.split("\n")
        findings_idx = next(
            i for i, line in enumerate(lines) if "Security Findings:" in line
        )
        docs_idx = next(
            i for i, line in enumerate(lines) if "Project Documents:" in line
        )
        assert findings_idx < docs_idx
        mock_retriever.search.assert_called_once()
        mock_store.search.assert_called_once()

    def test_mode_documents_with_no_store_returns_empty_string(
        self,
    ) -> None:
        """Mode 'documents' with no store returns empty string."""
        mock_retriever = MagicMock()

        context = _retrieve_context(
            mock_retriever,
            "some query",
            document_store=None,
            mode="documents",
        )

        assert context == ""
        mock_retriever.search.assert_not_called()

    def test_mode_findings_when_retriever_search_raises_returns_empty(
        self,
    ) -> None:
        """Mode 'findings' when search raises returns empty string."""
        mock_retriever = MagicMock()
        mock_retriever.search.side_effect = RuntimeError("Search failed")

        context = _retrieve_context(
            mock_retriever,
            "query",
            mode="findings",
        )

        assert context == ""
        mock_retriever.search.assert_called_once()

    def test_mode_all_with_no_results_returns_empty_string(
        self,
    ) -> None:
        """Mode 'all' with no results returns empty string."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []
        mock_store = MagicMock()
        mock_store.search.return_value = []

        context = _retrieve_context(
            mock_retriever,
            "query",
            document_store=mock_store,
            mode="all",
        )

        assert context == ""

    def test_mode_all_with_empty_findings_but_documents_present(
        self,
    ) -> None:
        """Mode 'all' with empty findings but documents returns docs only."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []
        mock_store = MagicMock()
        mock_store.search.return_value = [
            _make_document_match("d1", "Setup instructions"),
        ]

        context = _retrieve_context(
            mock_retriever,
            "setup",
            document_store=mock_store,
            mode="all",
        )

        assert "Project Documents:" in context
        assert "Setup instructions" in context
        assert "Security Findings:" not in context

    def test_mode_all_with_findings_but_no_documents_returns_findings_only(
        self,
    ) -> None:
        """Mode 'all' with findings but no documents returns findings only."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_finding_match("f1", "Critical vulnerability"),
        ]
        mock_store = MagicMock()
        mock_store.search.return_value = []

        context = _retrieve_context(
            mock_retriever,
            "vulnerabilities",
            document_store=mock_store,
            mode="all",
        )

        assert "Security Findings:" in context
        assert "Critical vulnerability" in context
        assert "Project Documents:" not in context

    def test_finding_match_with_empty_metadata_formats_correctly(
        self,
    ) -> None:
        """Finding match with empty metadata still formats."""
        mock_retriever = MagicMock()
        match: VectorMatch = {
            "id": "f1",
            "document": "Some finding text",
            "metadata": {},
            "distance": 0.1,
        }
        mock_retriever.search.return_value = [match]

        context = _retrieve_context(
            mock_retriever,
            "query",
            mode="findings",
        )

        assert "Some finding text" in context
        assert "Security Findings:" in context

    def test_document_match_with_missing_source_file_shows_unknown(
        self,
    ) -> None:
        """Document match with missing source_file shows 'unknown'."""
        mock_retriever = MagicMock()
        mock_store = MagicMock()
        match: VectorMatch = {
            "id": "d1",
            "document": "Some document content",
            "metadata": {"source_type": "user_doc"},
            "distance": 0.2,
        }
        mock_store.search.return_value = [match]

        context = _retrieve_context(
            mock_retriever,
            "query",
            document_store=mock_store,
            mode="documents",
        )

        assert "[doc: unknown]" in context
        assert "Some document content" in context

    def test_finding_numbered_list_starts_at_one(self) -> None:
        """Finding list numbering starts at 1."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_finding_match("f1", "First finding"),
            _make_finding_match("f2", "Second finding"),
            _make_finding_match("f3", "Third finding"),
        ]

        context = _retrieve_context(
            mock_retriever,
            "query",
            mode="findings",
        )

        lines = context.split("\n")
        finding_lines = [
            line for line in lines if line and line[0].isdigit() and "." in line
        ]
        assert "1." in finding_lines[0]
        assert "2." in finding_lines[1]
        assert "3." in finding_lines[2]

    def test_mode_default_is_all(self) -> None:
        """Mode parameter defaults to 'all'."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_finding_match("f1", "Finding text"),
        ]
        mock_store = MagicMock()
        mock_store.search.return_value = [
            _make_document_match("d1", "Document text"),
        ]

        context = _retrieve_context(
            mock_retriever,
            "query",
            document_store=mock_store,
        )

        assert "Security Findings:" in context
        assert "Project Documents:" in context

    def test_document_store_search_called_with_correct_n_results(
        self,
    ) -> None:
        """Document store search is called with min(20, 5) results."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []
        mock_store = MagicMock()
        mock_store.search.return_value = []

        _retrieve_context(
            mock_retriever,
            "query",
            document_store=mock_store,
            mode="all",
        )

        call_kwargs = mock_store.search.call_args[1]
        assert call_kwargs["n_results"] == 5

    def test_retriever_search_called_with_correct_n_results(
        self,
    ) -> None:
        """Retriever search is called with RETRIEVAL_N_RESULTS."""
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []

        _retrieve_context(
            mock_retriever,
            "query",
            mode="findings",
        )

        call_kwargs = mock_retriever.search.call_args[1]
        assert call_kwargs["n_results"] == 20

    def test_finding_with_no_profile_omits_repo_part(self) -> None:
        """Finding with no profile omits 'repo=' part."""
        mock_retriever = MagicMock()
        match: VectorMatch = {
            "id": "f1",
            "document": "Finding text",
            "metadata": {"tool": "semgrep", "profile": ""},
            "distance": 0.1,
        }
        mock_retriever.search.return_value = [match]

        context = _retrieve_context(
            mock_retriever,
            "query",
            mode="findings",
        )

        assert "[semgrep]" in context
        assert "repo=" not in context

    def test_mode_documents_when_store_search_raises_returns_empty(
        self,
    ) -> None:
        """Mode 'documents' when store search raises returns empty string."""
        mock_retriever = MagicMock()
        mock_store = MagicMock()
        mock_store.search.side_effect = RuntimeError("Store search failed")

        context = _retrieve_context(
            mock_retriever,
            "query",
            document_store=mock_store,
            mode="documents",
        )

        assert context == ""
