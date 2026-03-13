"""Unit tests for OllamaEmbeddingAdapter and get_embedding_provider factory."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.embedding import (
    OllamaEmbeddingAdapter,
    get_embedding_provider,
)

_URL = "http://localhost:11434"
_MODEL = "nomic-embed-text:latest"


@pytest.fixture()
def adapter() -> OllamaEmbeddingAdapter:
    return OllamaEmbeddingAdapter(
        base_url=_URL,
        model=_MODEL,
        timeout_seconds=10,
    )


# ---------------------------------------------------------------------------
# TestIsAvailable
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestEmbed
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestFactory
# ---------------------------------------------------------------------------


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "chat_llm_provider": "ollama",
        "enrichment_llm_provider": "ollama",
        "report_llm_provider": "ollama",
        "embedding_provider": "ollama_embedding",
        "ollama": {"base_url": _URL, "model": "qwen3:14b"},
        "ollama_embedding": {"model": _MODEL},
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestFactory:
    def test_returns_ollama_embedding_adapter(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_embedding_provider(tmp_path)
        assert isinstance(provider, OllamaEmbeddingAdapter)

    def test_raises_on_unknown_provider(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path, {"embedding_provider": "unknown"})
        with pytest.raises(ValueError, match="unknown"):
            get_embedding_provider(tmp_path)
