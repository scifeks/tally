"""Unit tests for OllamaEmbeddingAdapter.embed."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.embedding.ollama_embedding_adapter import OllamaEmbeddingAdapter

_URL = "http://localhost:11434"
_MODEL = "nomic-embed-text:latest"


@pytest.fixture()
def adapter() -> OllamaEmbeddingAdapter:
    return OllamaEmbeddingAdapter(
        base_url=_URL,
        model=_MODEL,
        timeout_seconds=10,
    )


class TestEmbed:
    def _mock_urlopen(self, vector: list[float]) -> MagicMock:
        body = json.dumps({"embedding": vector}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_float_vector(self, adapter: OllamaEmbeddingAdapter) -> None:
        vector = [0.1, 0.2, 0.3]
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(vector)):
            result = adapter.embed("hello")
        assert result == vector

    def test_calls_embeddings_endpoint(self, adapter: OllamaEmbeddingAdapter) -> None:
        vector = [0.0]
        with patch(
            "urllib.request.urlopen", return_value=self._mock_urlopen(vector)
        ) as mock_open:
            adapter.embed("text")
        req = mock_open.call_args[0][0]
        assert "/api/embeddings" in req.full_url

    def test_error_propagates(self, adapter: OllamaEmbeddingAdapter) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("network failure")):
            with pytest.raises(OSError):
                adapter.embed("text")
