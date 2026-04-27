"""Tests for core.config._atomic — locking and atomic write.

``sweep_orphans`` lives in ``test_sweep_orphans.py``.
"""

from __future__ import annotations

import multiprocessing
import threading
import time
from pathlib import Path

import pytest

from core.config._atomic import (
    atomic_write_text,
    locked_config,
)


def test_atomic_write_text_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_write_text(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_atomic_write_text_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dirs" / "out.json"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_text_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_text_no_orphan_tmp_on_success(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_write_text(target, "ok")
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_locked_config_creates_sidecar_lock(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text("{}", encoding="utf-8")
    with locked_config(target):
        lock_path = target.with_name(target.name + ".lock")
        assert lock_path.exists()


def test_locked_config_serializes_in_process_threads(tmp_path: Path) -> None:
    """Two threads racing on the same path must serialize, no lost update."""
    target = tmp_path / "counter.txt"
    target.write_text("0", encoding="utf-8")
    iterations = 50

    def increment(n: int) -> None:
        for _ in range(n):
            with locked_config(target):
                cur = int(target.read_text(encoding="utf-8"))
                # Encourage a race: yield the GIL and sleep briefly.
                time.sleep(0.001)
                atomic_write_text(target, str(cur + 1))

    threads = [
        threading.Thread(target=increment, args=(iterations,)),
        threading.Thread(target=increment, args=(iterations,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = int(target.read_text(encoding="utf-8"))
    assert final == iterations * 2


def _child_increment(target_str: str, iterations: int) -> None:
    """Worker for the cross-process lock test."""
    from core.config._atomic import (
        atomic_write_text as _aw,
    )
    from core.config._atomic import (
        locked_config as _lc,
    )

    target = Path(target_str)
    for _ in range(iterations):
        with _lc(target):
            cur = int(target.read_text(encoding="utf-8"))
            time.sleep(0.001)
            _aw(target, str(cur + 1))


def test_locked_config_serializes_across_processes(tmp_path: Path) -> None:
    """fcntl.flock(LOCK_EX) prevents lost updates across two processes."""
    target = tmp_path / "counter.txt"
    target.write_text("0", encoding="utf-8")
    iterations = 20

    # Use "spawn" — pytest pulls in pytest-asyncio etc., and Python 3.14
    # warns on fork() from multi-threaded processes.
    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(target=_child_increment, args=(str(target), iterations)),
        ctx.Process(target=_child_increment, args=(str(target), iterations)),
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    final = int(target.read_text(encoding="utf-8"))
    assert final == iterations * 2


def test_locked_config_releases_on_exception(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with locked_config(target):
            raise RuntimeError("boom")
    # If the lock weren't released, this would block forever; pytest will
    # time out a hung test but a clean acquire here proves cleanup happened.
    with locked_config(target):
        pass
