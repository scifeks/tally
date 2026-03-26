"""Unit tests for is_test_path test-directory filtering."""

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
    def test_returns_true_for_file_in_test_dir(self) -> None:
        assert is_test_path("/tests/x.py", ["tests"]) is True

    def test_returns_false_for_src_file(self) -> None:
        assert is_test_path("/src/x.py", ["tests"]) is False

    def test_returns_true_for_exact_test_dir_path(self) -> None:
        assert is_test_path("/tests", ["tests"]) is True

    def test_returns_false_when_test_dirs_empty(self) -> None:
        assert is_test_path("/tests/x.py", []) is False

    def test_does_not_match_partial_dir_name(self) -> None:
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
