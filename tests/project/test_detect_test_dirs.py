"""Tests for _detect_test_dirs() in core.project.manager."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project.wizard import _detect_test_dirs  # noqa: E402


class TestDetectTestDirs:
    def test_detects_known_names(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "spec").mkdir()
        (tmp_path / "src").mkdir()
        result = _detect_test_dirs(tmp_path)
        assert result == ["spec", "tests"]

    def test_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "lib").mkdir()
        result = _detect_test_dirs(tmp_path)
        assert result == []

    def test_ignores_files(self, tmp_path: Path) -> None:
        # "tests" is a file, not a directory — should not be detected
        (tmp_path / "tests").write_text("")
        result = _detect_test_dirs(tmp_path)
        assert result == []

    def test_detects_all_five_names(self, tmp_path: Path) -> None:
        for name in ("test", "tests", "spec", "__tests__", "e2e"):
            (tmp_path / name).mkdir()
        result = _detect_test_dirs(tmp_path)
        assert result == sorted(["test", "tests", "spec", "__tests__", "e2e"])

    def test_does_not_scan_subdirs(self, tmp_path: Path) -> None:
        # tests/ nested inside src/ should not be detected (top-level only)
        src = tmp_path / "src"
        src.mkdir()
        (src / "tests").mkdir()
        result = _detect_test_dirs(tmp_path)
        assert result == []
