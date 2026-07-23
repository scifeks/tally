"""Unit tests for VoyageEmbeddingAdapter.embed()."""

from __future__ import annotations

import importlib.util
from unittest.mock import MagicMock, patch

import pytest

if not importlib.util.find_spec("voyageai"):
    pytest.skip("voyageai not installed", allow_module_level=True)

from application.ports.embedding_provider import (
    EmbeddingAdapterError,
)
from infrastructure.embedding.voyage_embedding_adapter import (
    VoyageEmbeddingAdapter,
)


class TestVoyageEmbeddingEmbed:
    def test_returns_embedding_vector(self) -> None:
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1, 0.2, 0.3]]

        with patch(
            "infrastructure.embedding.voyage_embedding_adapter.VoyageClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.embed.return_value = mock_result
            adapter = VoyageEmbeddingAdapter(
                api_key="pa-test-key",
                model="voyage-3",
            )
            result = adapter.embed("hello world")

        assert result == [0.1, 0.2, 0.3]

    def test_calls_embed_with_correct_args(self) -> None:
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1]]

        with patch(
            "infrastructure.embedding.voyage_embedding_adapter.VoyageClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.embed.return_value = mock_result
            adapter = VoyageEmbeddingAdapter(
                api_key="pa-test-key",
                model="voyage-3",
            )
            adapter.embed("test text")

        mock_client.embed.assert_called_once_with(texts=["test text"], model="voyage-3")

    def test_wraps_errors_in_embedding_adapter_error(self) -> None:
        with patch(
            "infrastructure.embedding.voyage_embedding_adapter.VoyageClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.embed.side_effect = RuntimeError("API error")
            adapter = VoyageEmbeddingAdapter(
                api_key="pa-test-key",
                model="voyage-3",
            )
            with pytest.raises(EmbeddingAdapterError):
                adapter.embed("test text")

    def test_uses_configured_timeout(self) -> None:
        adapter = VoyageEmbeddingAdapter(
            api_key="pa-test-key",
            model="voyage-3",
            timeout_seconds=120,
        )
        assert adapter._timeout == 120

    def test_passes_model_from_constructor(self) -> None:
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1]]

        with patch(
            "infrastructure.embedding.voyage_embedding_adapter.VoyageClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.embed.return_value = mock_result
            adapter = VoyageEmbeddingAdapter(
                api_key="pa-test-key",
                model="voyage-large-2-1.5",
            )
            adapter.embed("test")

        mock_client.embed.assert_called_once_with(
            texts=["test"], model="voyage-large-2-1.5"
        )
