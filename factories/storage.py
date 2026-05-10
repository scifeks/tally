"""Storage adapter factory functions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from infrastructure.storage.arg_files import ArgFilesStorageAdapter

if TYPE_CHECKING:
    from application.ports.arg_files_storage import ArgFilesStoragePort


def create_arg_files_storage(
    arg_files_dir: Path,
) -> ArgFilesStoragePort:
    """Create an ArgFilesStorageAdapter."""
    return ArgFilesStorageAdapter(arg_files_dir)
