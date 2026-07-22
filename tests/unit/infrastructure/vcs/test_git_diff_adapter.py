"""Tests for GitDiffAdapter."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from application.ports.subprocess_runner import (
    SubprocessResult,
    SubprocessRunnerPort,
)
from infrastructure.vcs.git_diff_adapter import GitDiffAdapter


class TestGitDiffAdapter:
    def test_parses_changed_files(self) -> None:
        runner = Mock(spec=SubprocessRunnerPort)
        runner.run.return_value = SubprocessResult(
            returncode=0,
            stdout="src/foo.py\nsrc/bar.py\n",
            stderr="",
        )
        adapter = GitDiffAdapter(runner)
        result = adapter.changed_files("/repo", "abc123")
        assert result == ["src/foo.py", "src/bar.py"]

    def test_empty_diff_returns_empty_list(self) -> None:
        runner = Mock(spec=SubprocessRunnerPort)
        runner.run.return_value = SubprocessResult(returncode=0, stdout="", stderr="")
        adapter = GitDiffAdapter(runner)
        assert adapter.changed_files("/repo", "HEAD~1") == []

    def test_bad_revision_raises_value_error(self) -> None:
        runner = Mock(spec=SubprocessRunnerPort)
        runner.run.return_value = SubprocessResult(
            returncode=128,
            stdout="",
            stderr="fatal: bad revision 'nonexistent'",
        )
        adapter = GitDiffAdapter(runner)
        with pytest.raises(ValueError, match="nonexistent"):
            adapter.changed_files("/repo", "nonexistent")

    def test_strips_whitespace_and_empty_lines(self) -> None:
        runner = Mock(spec=SubprocessRunnerPort)
        runner.run.return_value = SubprocessResult(
            returncode=0,
            stdout="  src/a.py  \n\n  src/b.py\n\n",
            stderr="",
        )
        adapter = GitDiffAdapter(runner)
        result = adapter.changed_files("/repo", "HEAD~2")
        assert result == ["src/a.py", "src/b.py"]

    def test_passes_correct_git_command(self) -> None:
        runner = Mock(spec=SubprocessRunnerPort)
        runner.run.return_value = SubprocessResult(returncode=0, stdout="", stderr="")
        adapter = GitDiffAdapter(runner)
        adapter.changed_files("/my/repo", "abc123")
        runner.run.assert_called_once_with(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                "abc123..HEAD",
            ],
            timeout=30,
            cwd="/my/repo",
        )

    @pytest.mark.parametrize(
        "bad_ref",
        [
            "--exec=evil",
            "-c",
            "abc; rm -rf /",
            "",
        ],
    )
    def test_rejects_malicious_refs(self, bad_ref: str) -> None:
        runner = Mock(spec=SubprocessRunnerPort)
        adapter = GitDiffAdapter(runner)
        with pytest.raises(ValueError):
            adapter.changed_files("/repo", bad_ref)
        runner.run.assert_not_called()
