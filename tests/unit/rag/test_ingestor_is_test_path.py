"""Unit tests for is_test_path."""

from __future__ import annotations

from application.rag.ingestor import _normalize_path, is_test_path
from core.config.schemas import Repository


def _repo(name: str, path: str, test_dirs: list[str] | None = None) -> Repository:
    return Repository.model_construct(
        name=name,
        path=path,
        type=["library"],
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=test_dirs if test_dirs is not None else [],
    )


class TestIsTestPath:
    def test_file_inside_test_dir_returns_true(self) -> None:
        assert is_test_path("/tests/foo.py", ["tests"]) is True

    def test_file_outside_test_dir_returns_false(self) -> None:
        assert is_test_path("/src/foo.py", ["tests"]) is False

    def test_exact_test_dir_path_returns_true(self) -> None:
        assert is_test_path("/tests", ["tests"]) is True

    def test_empty_test_dirs_returns_false(self) -> None:
        assert is_test_path("/tests/foo.py", []) is False

    def test_multiple_test_dirs_matches_any(self) -> None:
        assert is_test_path("/spec/auth_spec.py", ["tests", "spec"]) is True

    def test_partial_name_not_matched(self) -> None:
        # /integration_tests/ should not match test dir "tests"
        assert is_test_path("/integration_tests/foo.py", ["tests"]) is False

    def test_does_not_match_prefix_partial_dir_name(self) -> None:
        assert is_test_path("/testsfoo/x.py", ["tests"]) is False

    def test_matches_nested_test_dir(self) -> None:
        assert is_test_path("/a/tests/x.py", ["a/tests"]) is True

    def test_unmatched_repo_gives_none_repo_name(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        _, repo_name = _normalize_path("/other/tests/x.py", repos)
        assert repo_name is None

    def test_matched_repo_gives_repo_name(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        rel, repo_name = _normalize_path("/repos/app/tests/x.py", repos)
        assert repo_name == "myapp"
        assert is_test_path(rel, ["tests"]) is True
