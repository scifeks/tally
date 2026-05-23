"""Unit tests for Repository.build_excluded_dirs."""

from __future__ import annotations

from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import build_excluded_dirs


def _service(test_dirs: list[str], ignore_dirs: list[str]) -> RepoService:
    return RepoService.model_construct(
        name="service",
        relative_path="",
        type=["api"],
        languages=["python"],
        docker_path="",
        container_name="",
        base_urls=[],
        test_dirs=test_dirs,
        ignore_dirs=ignore_dirs,
    )


class TestBuildExcludedDirs:
    def test_combines_test_and_ignore_dirs(self) -> None:
        service = _service(["tests"], ["vendor"])
        assert build_excluded_dirs(service) == ["tests", "vendor"]

    def test_deduplicates_overlapping_entries(self) -> None:
        service = _service(["tests"], ["tests", "vendor"])
        assert build_excluded_dirs(service) == ["tests", "vendor"]

    def test_empty_both_fields(self) -> None:
        service = _service([], [])
        assert build_excluded_dirs(service) == []

    def test_only_test_dirs(self) -> None:
        service = _service(["spec", "tests"], [])
        assert build_excluded_dirs(service) == ["spec", "tests"]

    def test_only_ignore_dirs(self) -> None:
        service = _service([], ["vendor", "node_modules"])
        assert build_excluded_dirs(service) == ["vendor", "node_modules"]

    def test_preserves_insertion_order(self) -> None:
        service = _service(["tests", "spec"], ["vendor", "mocks"])
        assert build_excluded_dirs(service) == ["tests", "spec", "vendor", "mocks"]
