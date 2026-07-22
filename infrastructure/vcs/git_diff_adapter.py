"""Git diff adapter using subprocess."""

from __future__ import annotations

import re

from application.ports.subprocess_runner import (
    SubprocessResult,
    SubprocessRunnerPort,
)

_VALID_REF = re.compile(r"^[A-Za-z0-9._/~^{}\-]{1,200}$")


class GitDiffAdapter:
    """Compute changed files via git diff subprocess."""

    def __init__(self, runner: SubprocessRunnerPort) -> None:
        self._runner = runner

    def changed_files(
        self,
        repo_path: str,
        since_commit: str,
    ) -> list[str]:
        if since_commit.startswith("-") or not _VALID_REF.match(since_commit):
            raise ValueError(f"invalid commit ref: {since_commit!r}")
        result: SubprocessResult = self._runner.run(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                f"{since_commit}..HEAD",
            ],
            timeout=30,
            cwd=repo_path,
        )
        if result.returncode != 0:
            raise ValueError(
                f"git diff failed for ref {since_commit!r}: {result.stderr.strip()}"
            )
        return [
            line.strip() for line in result.stdout.strip().splitlines() if line.strip()
        ]
