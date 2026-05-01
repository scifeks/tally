"""Unit tests for OllamaAdapter.is_available."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.llm.ollama_adapter import OllamaAdapter

_URL = "http://localhost:11434"
_MODEL = "qwen3:14b"


@pytest.fixture()
def adapter() -> OllamaAdapter:
    return OllamaAdapter(
        base_url=_URL,
        model=_MODEL,
        timeout_seconds=10,
    )


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
