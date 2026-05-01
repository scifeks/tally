"""Unit tests for OllamaEmbeddingAdapter.is_available."""

from __future__ import annotations

import urllib.error
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


class TestIsAvailable:
    def test_returns_true_on_200(self, adapter: OllamaEmbeddingAdapter) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert adapter.is_available() is True

    def test_returns_false_on_url_error(self, adapter: OllamaEmbeddingAdapter) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        ):
            assert adapter.is_available() is False

    def test_returns_false_on_os_error(self, adapter: OllamaEmbeddingAdapter) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("conn")):
            assert adapter.is_available() is False
