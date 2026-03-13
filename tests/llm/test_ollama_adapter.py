"""Unit tests for OllamaAdapter — all HTTP calls mocked."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from core.llm.ollama_adapter import OllamaAdapter

_URL = "http://localhost:11434"
_MODEL = "qwen3:14b"
_EMBED_MODEL = "nomic-embed-text:latest"


@pytest.fixture()
def adapter() -> OllamaAdapter:
    return OllamaAdapter(
        base_url=_URL,
        model=_MODEL,
        embedding_model=_EMBED_MODEL,
        timeout_seconds=10,
    )


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_true_on_200(self, adapter: OllamaAdapter) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert adapter.is_available() is True

    def test_returns_false_on_url_error(self, adapter: OllamaAdapter) -> None:
        with patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("refused")
        ):
            assert adapter.is_available() is False

    def test_returns_false_on_os_error(self, adapter: OllamaAdapter) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("conn")):
            assert adapter.is_available() is False


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


class TestChat:
    def _make_ollama_response(self, content: str) -> MagicMock:
        msg = MagicMock()
        msg.content = content
        resp = MagicMock()
        resp.message = msg
        return resp

    def test_returns_content(self, adapter: OllamaAdapter) -> None:
        fake_resp = self._make_ollama_response("hello world")
        with patch("ollama.Client") as MockClient:
            MockClient.return_value.chat.return_value = fake_resp
            result = adapter.chat([{"role": "user", "content": "hi"}])
        assert result == "hello world"

    def test_kwargs_merged_into_options(self, adapter: OllamaAdapter) -> None:
        fake_resp = self._make_ollama_response("ok")
        with patch("ollama.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.return_value = fake_resp
            adapter.chat(
                [{"role": "user", "content": "q"}],
                temperature=0.5,
                num_predict=100,
            )
            _, call_kwargs = mock_instance.chat.call_args
            assert call_kwargs["options"] == {"temperature": 0.5, "num_predict": 100}

    def test_exception_propagates(self, adapter: OllamaAdapter) -> None:
        with patch("ollama.Client") as MockClient:
            MockClient.return_value.chat.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError, match="boom"):
                adapter.chat([{"role": "user", "content": "q"}])


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------


class TestComplete:
    def test_delegates_to_chat(self, adapter: OllamaAdapter) -> None:
        with patch.object(adapter, "chat", return_value="result") as mock_chat:
            out = adapter.complete("my prompt", temperature=0.3)
        mock_chat.assert_called_once_with(
            [{"role": "user", "content": "my prompt"}], temperature=0.3
        )
        assert out == "result"


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


class TestEmbed:
    def _mock_urlopen(self, vector: list[float]) -> MagicMock:
        body = json.dumps({"embedding": vector}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_float_vector(self, adapter: OllamaAdapter) -> None:
        vector = [0.1, 0.2, 0.3]
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(vector)):
            result = adapter.embed("hello")
        assert result == vector

    def test_calls_embeddings_endpoint(self, adapter: OllamaAdapter) -> None:
        vector = [0.0]
        with patch(
            "urllib.request.urlopen", return_value=self._mock_urlopen(vector)
        ) as mock_open:
            adapter.embed("text")
        req = mock_open.call_args[0][0]
        assert "/api/embeddings" in req.full_url

    def test_error_propagates(self, adapter: OllamaAdapter) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("network failure")):
            with pytest.raises(OSError):
                adapter.embed("text")
