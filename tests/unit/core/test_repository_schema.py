"""Unit tests for Repository.build_excluded_dirs."""

from __future__ import annotations

from core.config.schemas.repository import Repository, build_excluded_dirs


def _repo(test_dirs: list[str], ignore_dirs: list[str]) -> Repository:
    return Repository.model_construct(
        name="r",
        type=["api"],
        path="/repo",
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=test_dirs,
        ignore_dirs=ignore_dirs,
    )


class TestBuildExcludedDirs:
    def test_combines_test_and_ignore_dirs(self) -> None:
        repo = _repo(["tests"], ["vendor"])
        assert build_excluded_dirs(repo) == ["tests", "vendor"]

    def test_deduplicates_overlapping_entries(self) -> None:
        repo = _repo(["tests"], ["tests", "vendor"])
        assert build_excluded_dirs(repo) == ["tests", "vendor"]

    def test_empty_both_fields(self) -> None:
        repo = _repo([], [])
        assert build_excluded_dirs(repo) == []

    def test_only_test_dirs(self) -> None:
        repo = _repo(["spec", "tests"], [])
        assert build_excluded_dirs(repo) == ["spec", "tests"]

    def test_only_ignore_dirs(self) -> None:
        repo = _repo([], ["vendor", "node_modules"])
        assert build_excluded_dirs(repo) == ["vendor", "node_modules"]

    def test_preserves_insertion_order(self) -> None:
        repo = _repo(["tests", "spec"], ["vendor", "mocks"])
        assert build_excluded_dirs(repo) == ["tests", "spec", "vendor", "mocks"]
