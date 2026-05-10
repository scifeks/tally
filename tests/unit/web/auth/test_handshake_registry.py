"""Unit tests for HandshakeRegistry."""

from __future__ import annotations

import time

import pytest

from web.auth.handshake import HandshakeRegistry


class TestRegisterAndConsume:
    def test_valid_token_consumed_successfully(self) -> None:
        reg = HandshakeRegistry()
        reg.register("abc")
        assert reg.consume("abc") is True

    def test_single_use_second_consume_fails(self) -> None:
        reg = HandshakeRegistry()
        reg.register("abc")
        reg.consume("abc")
        assert reg.consume("abc") is False

    def test_unknown_token_returns_false(self) -> None:
        reg = HandshakeRegistry()
        assert reg.consume("no-such-token") is False

    def test_different_tokens_are_independent(self) -> None:
        reg = HandshakeRegistry()
        reg.register("tok-a")
        reg.register("tok-b")
        assert reg.consume("tok-a") is True
        assert reg.consume("tok-b") is True


class TestTTL:
    def test_token_valid_within_ttl(self) -> None:
        reg = HandshakeRegistry(ttl=60.0)
        reg.register("fresh")
        assert reg.consume("fresh") is True

    def test_expired_token_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = HandshakeRegistry(ttl=1.0)
        reg.register("old")
        future = time.monotonic() + 100.0
        monkeypatch.setattr("web.auth.handshake.time.monotonic", lambda: future)
        assert reg.consume("old") is False
