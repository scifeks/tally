"""Unit tests for SessionStore."""

from __future__ import annotations

from web.auth.sessions import SessionStore


class TestCreate:
    def test_returns_two_non_empty_strings(self) -> None:
        store = SessionStore()
        session_id, csrf_token = store.create()
        assert session_id and csrf_token

    def test_each_create_returns_unique_values(self) -> None:
        store = SessionStore()
        id_a, csrf_a = store.create()
        id_b, csrf_b = store.create()
        assert id_a != id_b
        assert csrf_a != csrf_b


class TestVerify:
    def test_valid_session_returns_true(self) -> None:
        store = SessionStore()
        session_id, _ = store.create()
        assert store.verify(session_id) is True

    def test_unknown_session_returns_false(self) -> None:
        store = SessionStore()
        assert store.verify("no-such-id") is False

    def test_revoked_session_returns_false(self) -> None:
        store = SessionStore()
        session_id, _ = store.create()
        store.revoke(session_id)
        assert store.verify(session_id) is False


class TestVerifyCsrf:
    def test_correct_token_returns_true(self) -> None:
        store = SessionStore()
        session_id, csrf_token = store.create()
        assert store.verify_csrf(session_id, csrf_token) is True

    def test_wrong_token_returns_false(self) -> None:
        store = SessionStore()
        session_id, _ = store.create()
        assert store.verify_csrf(session_id, "wrong-token") is False

    def test_unknown_session_returns_false(self) -> None:
        store = SessionStore()
        assert store.verify_csrf("no-such-id", "any-token") is False

    def test_empty_token_returns_false(self) -> None:
        store = SessionStore()
        session_id, _ = store.create()
        assert store.verify_csrf(session_id, "") is False


class TestRevoke:
    def test_revoke_removes_session(self) -> None:
        store = SessionStore()
        session_id, _ = store.create()
        store.revoke(session_id)
        assert store.verify(session_id) is False

    def test_revoke_unknown_is_silent(self) -> None:
        store = SessionStore()
        store.revoke("no-such-id")  # must not raise
