"""Port for computing changed files between git revisions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GitDiffPort(Protocol):
    """Compute files changed between a commit and HEAD."""

    def changed_files(
        self,
        repo_path: str,
        since_commit: str,
    ) -> list[str]:
        """Return relative paths changed since the given commit.

        Only includes added, copied, modified, and renamed files
        (not deleted). Raises ValueError if the commit ref cannot
        be resolved in the repository.
        """
        ...
