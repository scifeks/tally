"""Unit tests for LlamaCppEmbeddingAdapter.is_available()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.embedding.llama_cpp_embedding_adapter import (
    LlamaCppEmbeddingAdapter,
)


class TestLlamaCppEmbeddingIsAvailable:
    def test_returns_true_on_200(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        with patch("urllib.request.urlopen") as mock:
            resp = MagicMock()
            resp.status = 200
            mock.return_value.__enter__.return_value = resp
            assert adapter.is_available() is True

    def test_returns_false_on_url_error(self) -> None:
        import urllib.error

        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        with patch("urllib.request.urlopen") as mock:
            mock.side_effect = urllib.error.URLError("refused")
            assert adapter.is_available() is False

    def test_returns_false_on_os_error(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        with patch("urllib.request.urlopen") as mock:
            mock.side_effect = OSError("unreachable")
            assert adapter.is_available() is False

    def test_uses_health_endpoint(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        with patch("urllib.request.urlopen") as mock:
            resp = MagicMock()
            resp.status = 200
            mock.return_value.__enter__.return_value = resp
            adapter.is_available()
            call_url = mock.call_args[0][0]
            assert call_url == "http://localhost:8000/health"
