"""Unit tests for reconstruct_abs_path."""

from __future__ import annotations

from application.findings.updater import reconstruct_abs_path


class TestUpdaterHelpers:
    def test_reconstruct_matching_repo(self) -> None:
        repos = [{"name": "myrepo", "path": "/home/user/myrepo/"}]
        result = reconstruct_abs_path("/src/main.py", "myrepo", repos)
        assert result == "/home/user/myrepo/src/main.py"

    def test_reconstruct_no_matching_repo(self) -> None:
        result = reconstruct_abs_path(
            "/src/main.py",
            "other",
            [{"name": "myrepo", "path": "/home/user/myrepo/"}],
        )
        assert result is None

    def test_reconstruct_file_is_none(self) -> None:
        result = reconstruct_abs_path(
            None, "myrepo", [{"name": "myrepo", "path": "/tmp/x/"}]
        )
        assert result is None

    def test_reconstruct_repo_name_is_none(self) -> None:
        result = reconstruct_abs_path(
            "/src/main.py", None, [{"name": "myrepo", "path": "/tmp/x/"}]
        )
        assert result is None

    def test_reconstruct_empty_repos(self) -> None:
        result = reconstruct_abs_path("/src/main.py", "myrepo", [])
        assert result is None

    def test_reconstruct_path_traversal_blocked(self) -> None:
        repos = [{"name": "myrepo", "path": "/home/user/myrepo/"}]
        result = reconstruct_abs_path("/../../../etc/passwd", "myrepo", repos)
        assert result is None

    def test_reconstruct_dotdot_sibling_blocked(self) -> None:
        repos = [{"name": "myrepo", "path": "/home/user/myrepo/"}]
        result = reconstruct_abs_path(
            "/src/../../other_repo/secret.key", "myrepo", repos
        )
        assert result is None
