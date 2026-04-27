"""Cross-process atomic config writes with sidecar fcntl locking.

Phase 9.1: load/modify/save races between the REPL, the web API, and the
scan event handlers are eliminated by:

1. ``locked_config(path)`` — a context manager that takes an exclusive
   advisory lock on a sidecar ``<path>.lock`` file via ``fcntl.flock``. The
   lock is held by an open file descriptor, so the kernel releases it on
   process death (clean or otherwise). A per-canonical-path
   ``threading.Lock`` is layered on top so async tasks within the same
   process serialize before reaching fcntl.

2. ``atomic_write_text(path, text)`` — writes to a randomly-named
   ``<path>.<rand>.tmp`` and ``os.replace``s into place. fsync before
   replace; the temp file is unlinked on failure.

3. ``sweep_orphans(base_path)`` — clears stale ``*.tmp`` files left by
   crashes mid-write. Idempotent; safe to call at startup.
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from secrets import token_hex
from weakref import WeakValueDictionary

_PATH_LOCKS: WeakValueDictionary[str, threading.Lock] = WeakValueDictionary()
_PATH_LOCKS_GUARD = threading.Lock()


def _in_process_lock_for(canonical: str) -> threading.Lock:
    """Return the singleton ``threading.Lock`` for *canonical*."""
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(canonical)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[canonical] = lock
        return lock


@contextmanager
def locked_config(path: Path) -> Iterator[Path]:
    """Hold an exclusive lock on a sidecar ``<path>.lock`` file.

    Layered: ``threading.Lock`` (in-process) wraps ``fcntl.flock``
    (cross-process). On process death the kernel closes the FD and the
    advisory lock is released automatically.
    """
    canonical = str(path.resolve())
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    inproc = _in_process_lock_for(canonical)
    with inproc:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield path
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* via a temp file + ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{token_hex(8)}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def sweep_orphans(base_path: Path, max_age_seconds: float = 60.0) -> int:
    """Remove orphaned ``*.tmp`` files older than *max_age_seconds*.

    Targets ``<base>/config/`` and ``<base>/projects/*/config/``. Returns
    the count of files removed. Idempotent; safe to call at startup.
    """
    cutoff = time.time() - max_age_seconds
    candidate_dirs: list[Path] = [base_path / "config"]
    projects_dir = base_path / "projects"
    if projects_dir.is_dir():
        for child in projects_dir.iterdir():
            if child.is_dir():
                candidate_dirs.append(child / "config")

    removed = 0
    for directory in candidate_dirs:
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if not entry.name.endswith(".tmp"):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                pass
    return removed
