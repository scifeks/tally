"""Filesystem adapter for arg-profile file uploads.

Satisfies ``ArgFilesStoragePort``. Files persist under
``<arg_files_dir>/<profile_id>/<arg_name>/<original_filename>``.
Writes are atomic via a sibling temp file plus ``os.replace``.
Path-traversal attempts raise ``ArgFileNameError``.
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

    def write(
        self,
        profile_id: int,
        arg_name: str,
        data: bytes,
        original_filename: str | None = None,
    ) -> str:
        arg_dir = self._arg_dir(profile_id, arg_name)
        disk_name = original_filename or arg_name
        self._validate_name(disk_name)
        arg_dir.mkdir(parents=True, exist_ok=True)
        target = arg_dir / disk_name
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=arg_dir,
            delete=False,
        ) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target)
        return f"{self._root.name}/{profile_id}/{arg_name}/{disk_name}"

    def read(self, profile_id: int, arg_name: str) -> bytes | None:
        arg_dir = self._arg_dir(profile_id, arg_name)
        target = self._find_file(arg_dir)
        if target is None:
            return None
        return target.read_bytes()

    def delete(self, profile_id: int, arg_name: str) -> None:
        arg_dir = self._arg_dir(profile_id, arg_name)
        if arg_dir.is_dir():
            shutil.rmtree(arg_dir)

    def delete_profile_dir(self, profile_id: int) -> None:
        profile_dir = self._root / str(profile_id)
        if profile_dir.is_dir():
            shutil.rmtree(profile_dir)

    def _arg_dir(self, profile_id: int, arg_name: str) -> Path:
        self._validate_name(arg_name)
        return self._root / str(profile_id) / arg_name

    @staticmethod
    def _find_file(arg_dir: Path) -> Path | None:
        """Return the single file inside an arg directory."""
        if not arg_dir.is_dir():
            return None
        files = [f for f in arg_dir.iterdir() if f.is_file()]
        return files[0] if files else None

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name:
            raise ArgFileNameError("name must not be empty")
        if "/" in name or "\\" in name or "\x00" in name:
            raise ArgFileNameError(f"name {name!r} contains a path separator")
        if name in {".", ".."}:
            raise ArgFileNameError(f"name {name!r} is reserved")
        candidate = Path(name)
        if candidate.is_absolute():
            raise ArgFileNameError(f"name {name!r} is absolute")
