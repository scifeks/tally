"""Unit tests for OllamaAdapter.chat."""

from __future__ import annotations

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


class TestChat:
    def _make_ollama_response(self, content: str) -> MagicMock:
        msg = MagicMock()
        msg.content = content
        resp = MagicMock()
        resp.message = msg
        return resp

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
