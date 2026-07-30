"""Integration test for completions shim with real Ollama."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestCompletionsShimIntegration:
    """Tests that require a running Ollama instance."""

    def test_non_streaming_roundtrip(self) -> None:
        pytest.skip("Requires running Ollama instance")

    def test_streaming_roundtrip(self) -> None:
        pytest.skip("Requires running Ollama instance")
