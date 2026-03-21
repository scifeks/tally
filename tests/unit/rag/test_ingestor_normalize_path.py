"""Unit tests for _normalize_path."""

from __future__ import annotations

from application.rag.ingestor import _normalize_path
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


class TestNormalizePath:
    def test_normalize_strips_prefix(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, repo_name = _normalize_path("/repos/app/src/main.py", repos)
        assert rel == "/src/main.py"
        assert repo_name == "myapp"

    def test_normalize_no_match_returns_original(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, repo_name = _normalize_path("/other/path/file.py", repos)
        assert rel == "/other/path/file.py"
        assert repo_name is None

    def test_normalize_empty_path_returns_empty(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, repo_name = _normalize_path("", repos)
        assert rel == ""
        assert repo_name is None

    def test_normalize_repo_path_with_trailing_slash(self) -> None:
        repos = [_repo("myapp", "/repos/app/")]
        rel, repo_name = _normalize_path("/repos/app/src/main.py", repos)
        assert rel == "/src/main.py"
        assert repo_name == "myapp"
        assert not rel.startswith("//")

    def test_normalize_leading_slash_present(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, _ = _normalize_path("/repos/app/foo/bar/baz.php", repos)
        assert rel.startswith("/")

    def test_normalize_empty_repo_list(self) -> None:
        rel, repo_name = _normalize_path("/some/file.py", [])
        assert rel == "/some/file.py"
        assert repo_name is None
