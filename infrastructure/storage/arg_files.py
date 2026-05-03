"""Filesystem adapter for arg-profile file uploads.

Satisfies ``ArgFilesStoragePort``. Files persist under
``<arg_files_dir>/<profile_id>/<arg_name>``. Writes are atomic via a
sibling temp file plus ``os.replace``. Path-traversal attempts on
``arg_name`` raise ``ArgFileNameError``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from application.ports.arg_files_storage import (
    ArgFileNameError,
    ArgFilesStoragePort,
)


class ArgFilesStorageAdapter(ArgFilesStoragePort):
    def __init__(self, arg_files_dir: Path) -> None:
        self._root = arg_files_dir

    def write(self, profile_id: int, arg_name: str, data: bytes) -> str:
        profile_dir = self._profile_dir(profile_id)
        target = self._safe_target(profile_dir, arg_name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=profile_dir,
            delete=False,
        ) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target)
        return f"{self._root.name}/{profile_id}/{arg_name}"

    def read(self, profile_id: int, arg_name: str) -> bytes | None:
        profile_dir = self._profile_dir(profile_id)
        target = self._safe_target(profile_dir, arg_name)
        if not target.is_file():
            return None
        return target.read_bytes()

    def delete(self, profile_id: int, arg_name: str) -> None:
        profile_dir = self._profile_dir(profile_id)
        target = self._safe_target(profile_dir, arg_name)
        if target.is_file():
            target.unlink()

    def delete_profile_dir(self, profile_id: int) -> None:
        profile_dir = self._profile_dir(profile_id)
        if profile_dir.is_dir():
            shutil.rmtree(profile_dir)

    def _profile_dir(self, profile_id: int) -> Path:
        return self._root / str(profile_id)

    @staticmethod
    def _safe_target(profile_dir: Path, arg_name: str) -> Path:
        if not arg_name:
            raise ArgFileNameError("arg name must not be empty")
        if "/" in arg_name or "\\" in arg_name or "\x00" in arg_name:
            raise ArgFileNameError(f"arg name {arg_name!r} contains a path separator")
        if arg_name in {".", ".."}:
            raise ArgFileNameError(f"arg name {arg_name!r} is reserved")
        candidate = Path(arg_name)
        if candidate.is_absolute():
            raise ArgFileNameError(f"arg name {arg_name!r} is absolute")
        target = (profile_dir / arg_name).resolve(strict=False)
        anchor = profile_dir.resolve(strict=False)
        if target != anchor and anchor not in target.parents:
            raise ArgFileNameError(f"arg name {arg_name!r} escapes profile directory")
        return target
