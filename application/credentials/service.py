"""Encryption key lifecycle operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from core.security.credentials import create_key_file, encrypt_value

if TYPE_CHECKING:
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from core.project_paths import ProjectPaths


class CredentialsService:
    """Manages encryption key lifecycle for project credentials."""

    def __init__(self, repo_port: ProjectRepoRepositoryPort) -> None:
        self._repos = repo_port

    def reencrypt_repos(self) -> None:
        """Re-read and re-write repos to trigger encryption."""
        for repo in self._repos.list_active():
            if repo.id is not None and repo.auth is not None:
                self._repos.update(repo.id, repo)

    def change_key(
        self,
        paths: ProjectPaths,
        passphrase: str,
        final_dest: Path,
    ) -> None:
        """Atomically rotate the encryption key."""
        repos_with_auth = [
            (repo.id, repo)
            for repo in self._repos.list_active()
            if repo.id is not None and repo.auth is not None
        ]

        temp_key = final_dest.with_suffix(".key.new")
        new_key = create_key_file(passphrase, temp_key)

        try:
            updates: list[tuple[int, str]] = []
            for repo_id, repo in repos_with_auth:
                assert repo.auth is not None
                auth_dump = repo.auth.model_dump()
                encrypted = encrypt_value(json.dumps(auth_dump), new_key)
                updates.append((repo_id, encrypted))
            self._repos.update_auth_json_bulk(updates)
        except Exception:
            temp_key.unlink(missing_ok=True)
            raise

        self._swap_key_files(paths.credentials_key, final_dest, temp_key)

    @staticmethod
    def _swap_key_files(key_path: Path, final_dest: Path, temp_key: Path) -> None:
        if key_path.is_symlink():
            old_target = key_path.resolve()
            key_path.unlink()
            if old_target.resolve() != final_dest.resolve() and old_target.exists():
                old_target.unlink()
        elif key_path.exists():
            key_path.unlink()

        if final_dest.resolve() != key_path.resolve():
            if final_dest.exists():
                final_dest.unlink()
            temp_key.rename(final_dest)
            os.symlink(final_dest, key_path)
        else:
            temp_key.rename(key_path)
