"""Unit tests for LlamaCppEmbeddingAdapter.embed()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.ports.embedding_provider import (
    EmbeddingAdapterError,
)
from infrastructure.embedding.llama_cpp_embedding_adapter import (
    LlamaCppEmbeddingAdapter,
)


class TestLlamaCppEmbeddingEmbed:
    def test_returns_embedding_vector(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        mock_data = MagicMock(embedding=[0.1, 0.2, 0.3])
        mock_response = MagicMock(data=[mock_data])

        with patch(
            "infrastructure.embedding.llama_cpp_embedding_adapter.openai"
        ) as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            result = adapter.embed("test text")

        assert result == [0.1, 0.2, 0.3]

    def test_uses_v1_base_url(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        mock_data = MagicMock(embedding=[0.1])
        mock_response = MagicMock(data=[mock_data])

        with patch(
            "infrastructure.embedding.llama_cpp_embedding_adapter.openai"
        ) as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            adapter.embed("text")

        call_kwargs = mock_oai.OpenAI.call_args[1]
        assert call_kwargs["base_url"] == ("http://localhost:8000/v1")
        assert call_kwargs["api_key"] == "not-needed"

    def test_wraps_errors(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
        )
        with patch(
            "infrastructure.embedding.llama_cpp_embedding_adapter.openai"
        ) as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.embeddings.create.side_effect = RuntimeError("fail")
            with pytest.raises(EmbeddingAdapterError):
                adapter.embed("text")

    def test_uses_configured_timeout(self) -> None:
        adapter = LlamaCppEmbeddingAdapter(
            base_url="http://localhost:8000",
            model="nomic-embed-text",
            timeout_seconds=120,
        )
        mock_data = MagicMock(embedding=[0.1])
        mock_response = MagicMock(data=[mock_data])

        with patch(
            "infrastructure.embedding.llama_cpp_embedding_adapter.openai"
        ) as mock_oai:
            mock_client = MagicMock()
            mock_oai.OpenAI.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            adapter.embed("text")

        call_kwargs = mock_oai.OpenAI.call_args[1]
        assert call_kwargs["timeout"] == 120
