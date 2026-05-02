"""Tests for ``core.config._atomic.sweep_orphans``."""

from __future__ import annotations

import os
import time
from pathlib import Path

from core.config._atomic import sweep_orphans


def test_sweep_orphans_removes_stale_tmp(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    stale = config_dir / "global.json.deadbeef.tmp"
    stale.write_text("partial", encoding="utf-8")
    old = time.time() - 120
    os.utime(stale, (old, old))

    removed = sweep_orphans(tmp_path)
    assert removed == 1
    assert not stale.exists()


def test_sweep_orphans_keeps_recent_tmp(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    fresh = config_dir / "global.json.cafe.tmp"
    fresh.write_text("partial", encoding="utf-8")

    removed = sweep_orphans(tmp_path)
    assert removed == 0
    assert fresh.exists()


def test_sweep_orphans_targets_project_config_dirs(tmp_path: Path) -> None:
    project_config = tmp_path / "projects" / "alpha" / "config"
    project_config.mkdir(parents=True)
    stale = project_config / "project.json.beef.tmp"
    stale.write_text("partial", encoding="utf-8")
    old = time.time() - 120
    os.utime(stale, (old, old))

    removed = sweep_orphans(tmp_path)
    assert removed == 1
    assert not stale.exists()


def test_sweep_orphans_idempotent_when_clean(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    assert sweep_orphans(tmp_path) == 0
    assert sweep_orphans(tmp_path) == 0


def test_sweep_orphans_skips_non_tmp_files(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    keep = config_dir / "global.json"
    keep.write_text("{}", encoding="utf-8")
    old = time.time() - 600
    os.utime(keep, (old, old))

    removed = sweep_orphans(tmp_path)
    assert removed == 0
    assert keep.exists()
