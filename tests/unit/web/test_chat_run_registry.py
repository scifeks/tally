"""Unit tests for ChatRunRegistry (Phase 8.8).

Mirrors ``tests/unit/web/test_report_run_registry.py`` style. Verifies
register / unregister / get / list_for_project / list_all / reset.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock

import pytest

from web.adapters.chat_run_registry import (
    ChatRunRegistry,
    get_chat_run_registry,
)


def _make_task() -> asyncio.Task[None]:
    """Return a Mock that is ``isinstance``-compatible with ``asyncio.Task``.

    The registry only stores the object as a handle field; nothing
    awaits or inspects it in these unit tests. Using a Mock avoids the
    ``coroutine never awaited`` runtime warning that real Task creation
    triggers when the loop never runs.
    """
    return cast("asyncio.Task[None]", MagicMock(spec=asyncio.Task))


@pytest.fixture()
def registry() -> Generator[ChatRunRegistry]:
    r = ChatRunRegistry()
    yield r
    r.reset()


def test_register_and_get_roundtrip(registry: ChatRunRegistry) -> None:
    task = _make_task()
    handle = registry.register(
        session_id=42, project_id=7, user_message_id=101, task=task
    )

    assert handle.session_id == 42
    assert handle.project_id == 7
    assert handle.user_message_id == 101
    assert handle.task is task

    got = registry.get(42)
    assert got is handle


def test_get_returns_none_for_unknown(registry: ChatRunRegistry) -> None:
    assert registry.get(123) is None


def test_unregister_removes_entry(registry: ChatRunRegistry) -> None:
    task = _make_task()
    registry.register(session_id=1, project_id=1, user_message_id=10, task=task)
    registry.unregister(1)
    assert registry.get(1) is None


def test_unregister_unknown_is_noop(registry: ChatRunRegistry) -> None:
    # Should not raise.
    registry.unregister(99)


def test_register_replaces_existing_entry(registry: ChatRunRegistry) -> None:
    t1 = _make_task()
    t2 = _make_task()
    registry.register(session_id=1, project_id=1, user_message_id=10, task=t1)
    registry.register(session_id=1, project_id=1, user_message_id=20, task=t2)

    got = registry.get(1)
    assert got is not None
    assert got.task is t2
    assert got.user_message_id == 20


def test_list_for_project_filters(registry: ChatRunRegistry) -> None:
    registry.register(session_id=1, project_id=10, user_message_id=1, task=_make_task())
    registry.register(session_id=2, project_id=10, user_message_id=2, task=_make_task())
    registry.register(session_id=3, project_id=99, user_message_id=3, task=_make_task())

    p10 = registry.list_for_project(10)
    p99 = registry.list_for_project(99)
    p_missing = registry.list_for_project(123)

    assert sorted(h.session_id for h in p10) == [1, 2]
    assert [h.session_id for h in p99] == [3]
    assert p_missing == []


def test_list_all_returns_every_handle(registry: ChatRunRegistry) -> None:
    registry.register(session_id=1, project_id=1, user_message_id=1, task=_make_task())
    registry.register(session_id=2, project_id=2, user_message_id=2, task=_make_task())
    assert sorted(h.session_id for h in registry.list_all()) == [1, 2]


def test_reset_clears_handles(registry: ChatRunRegistry) -> None:
    registry.register(session_id=1, project_id=1, user_message_id=1, task=_make_task())
    registry.reset()
    assert registry.list_all() == []


def test_module_singleton_is_shared() -> None:
    a = get_chat_run_registry()
    b = get_chat_run_registry()
    assert a is b
    a.reset()
