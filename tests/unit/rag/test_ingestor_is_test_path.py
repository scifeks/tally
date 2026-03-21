"""Unit tests for _is_test_path."""

from __future__ import annotations

from application.rag.ingestor import _is_test_path


class TestIsTestPath:
    def test_file_inside_test_dir_returns_true(self) -> None:
        assert _is_test_path("/tests/foo.py", ["tests"]) is True

    def test_file_outside_test_dir_returns_false(self) -> None:
        assert _is_test_path("/src/foo.py", ["tests"]) is False

    def test_exact_test_dir_path_returns_true(self) -> None:
        assert _is_test_path("/tests", ["tests"]) is True

    def test_empty_test_dirs_returns_false(self) -> None:
        assert _is_test_path("/tests/foo.py", []) is False

    def test_multiple_test_dirs_matches_any(self) -> None:
        assert _is_test_path("/spec/auth_spec.py", ["tests", "spec"]) is True

    def test_partial_name_not_matched(self) -> None:
        # /integration_tests/ should not match test dir "tests"
        assert _is_test_path("/integration_tests/foo.py", ["tests"]) is False
