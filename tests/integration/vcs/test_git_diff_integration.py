"""Integration tests for GitDiffAdapter with real git repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from infrastructure.tools.runner import SubprocessRunner
from infrastructure.vcs.git_diff_adapter import GitDiffAdapter

pytestmark = pytest.mark.integration


class TestGitDiffAdapterIntegration:
    @staticmethod
    def _init_repo(tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "initial.py").write_text("x = 1\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        return repo

    @staticmethod
    def _get_head(repo: Path) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def test_detects_changed_files(self, tmp_path: Path) -> None:
        repo = self._init_repo(tmp_path)
        commit = self._get_head(repo)

        (repo / "new_file.py").write_text("y = 2\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        adapter = GitDiffAdapter(SubprocessRunner())
        changed = adapter.changed_files(str(repo), commit)
        assert changed == ["new_file.py"]

    def test_no_changes_returns_empty(self, tmp_path: Path) -> None:
        repo = self._init_repo(tmp_path)
        commit = self._get_head(repo)

        adapter = GitDiffAdapter(SubprocessRunner())
        assert adapter.changed_files(str(repo), commit) == []

    def test_invalid_commit_raises(self, tmp_path: Path) -> None:
        repo = self._init_repo(tmp_path)
        adapter = GitDiffAdapter(SubprocessRunner())
        with pytest.raises(ValueError):
            adapter.changed_files(str(repo), "nonexistent_ref")

    def test_multiple_changes_across_dirs(self, tmp_path: Path) -> None:
        repo = self._init_repo(tmp_path)
        commit = self._get_head(repo)

        (repo / "src").mkdir()
        (repo / "src" / "a.py").write_text("a = 1\n")
        (repo / "src" / "b.py").write_text("b = 2\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add files"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        adapter = GitDiffAdapter(SubprocessRunner())
        changed = adapter.changed_files(str(repo), commit)
        assert sorted(changed) == ["src/a.py", "src/b.py"]

    def test_deleted_files_excluded(self, tmp_path: Path) -> None:
        repo = self._init_repo(tmp_path)
        commit = self._get_head(repo)

        (repo / "initial.py").unlink()
        (repo / "replacement.py").write_text("z = 3\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "delete and add"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        adapter = GitDiffAdapter(SubprocessRunner())
        changed = adapter.changed_files(str(repo), commit)
        assert "initial.py" not in changed
        assert "replacement.py" in changed
