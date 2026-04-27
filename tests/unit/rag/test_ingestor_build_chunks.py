"""Unit tests for normalize_file_path path normalization."""

from __future__ import annotations

from application.rag.ingestor import normalize_file_path
from core.config.schemas import Repository


def _repo(name: str, path: str, repo_id: int = 1) -> Repository:
    return Repository.model_construct(
        id=repo_id,
        name=name,
        path=path,
        type=["library"],
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=[],
    )


class TestNormalizeFilePath:
    def test_strips_repo_prefix_from_absolute_path(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        result = normalize_file_path("/repos/app/src/main.py", repos)
        assert result is not None
        assert result[0] == "/src/main.py"
        assert "/repos/app" not in result[0]

    def test_sets_repo_name_when_prefix_matched(self) -> None:
        repos = [_repo("myapp", "/repos/app", repo_id=99)]
        result = normalize_file_path("/repos/app/src/main.py", repos)
        assert result is not None
        assert result[1] == 99

    def test_returns_none_for_empty_file_path(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        result = normalize_file_path("", repos)
        assert result is None

    def test_returns_path_unchanged_when_repos_empty(self) -> None:
        result = normalize_file_path("/repos/app/src/main.py", [])
        assert result == ("/repos/app/src/main.py", None)

    def test_returns_path_unchanged_when_no_repo_matches(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        result = normalize_file_path("/other/path/file.py", repos)
        assert result is not None
        assert result[0] == "/other/path/file.py"
        assert result[1] is None

    def test_with_repo_name_strips_prefix_for_absolute_path(self) -> None:
        repos = [_repo("myapp", "/repos/app", repo_id=11)]
        result = normalize_file_path("/repos/app/src/main.py", repos, repo_name="myapp")
        assert result == ("/src/main.py", 11)

    def test_with_repo_name_returns_path_unchanged_when_no_prefix_match(
        self,
    ) -> None:
        repos = [_repo("myapp", "/repos/app", repo_id=22)]
        result = normalize_file_path("config/aws.js", repos, repo_name="myapp")
        assert result == ("config/aws.js", 22)
