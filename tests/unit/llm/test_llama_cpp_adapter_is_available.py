"""Unit tests for LlamaCppAdapter.is_available()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.llm.llama_cpp_adapter import LlamaCppAdapter

_URL = "http://localhost:8000"
_MODEL = "llama2"


@pytest.fixture()
def adapter() -> LlamaCppAdapter:
    return LlamaCppAdapter(
        base_url=_URL,
        model=_MODEL,
        timeout_seconds=10,
    )


class TestIsAvailable:
    def test_uses_health_endpoint(self, adapter: LlamaCppAdapter) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            adapter.is_available()
            call_url = mock_open.call_args[0][0]
            assert call_url == f"{_URL}/health"
