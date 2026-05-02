"""Unit tests for CancellationToken."""

from __future__ import annotations

import threading

from application.locking.cancellation import CancellationToken, no_op_token


def test_default_token_is_unset() -> None:
    t = CancellationToken()
    assert t.is_set() is False


def test_set_marks_token() -> None:
    t = CancellationToken()
    t.set()
    assert t.is_set() is True


def test_set_is_idempotent() -> None:
    t = CancellationToken()
    t.set()
    t.set()
    assert t.is_set() is True


def test_wait_returns_true_when_set() -> None:
    t = CancellationToken()
    threading.Timer(0.01, t.set).start()
    assert t.wait(timeout=1.0) is True


def test_wait_returns_false_on_timeout() -> None:
    t = CancellationToken()
    assert t.wait(timeout=0.05) is False


def test_no_op_token_is_singleton_and_unset() -> None:
    a = no_op_token()
    b = no_op_token()
    assert a is b
    assert a.is_set() is False


def test_token_is_thread_safe() -> None:
    t = CancellationToken()
    seen: list[bool] = []

    def watcher() -> None:
        seen.append(t.wait(timeout=1.0))

    th = threading.Thread(target=watcher)
    th.start()
    t.set()
    th.join(timeout=2.0)
    assert seen == [True]
