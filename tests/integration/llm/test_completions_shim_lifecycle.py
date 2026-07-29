"""Integration tests for completions shim lifecycle."""

from __future__ import annotations

import socket

import pytest

from infrastructure.llm.completions_shim import CompletionsShim

pytestmark = pytest.mark.integration


class TestCompletionsShimLifecycle:
    """Tests for CompletionsShim startup and shutdown."""

    def test_start_returns_url(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "test-model")
        url = shim.start()
        try:
            assert url.startswith("http://127.0.0.1:")
            port_str = url.split(":")[-1]
            port = int(port_str)
            assert 1024 <= port <= 65535
        finally:
            shim.stop()

    def test_stop_shuts_down(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "test-model")
        url = shim.start()
        port = int(url.split(":")[-1])
        shim.stop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex(("127.0.0.1", port))
            assert result != 0
        finally:
            sock.close()

    def test_double_stop_is_safe(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "test-model")
        shim.start()
        shim.stop()
        shim.stop()
