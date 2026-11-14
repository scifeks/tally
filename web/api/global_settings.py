"""Global settings API: filesystem browsing."""

from __future__ import annotations

import stat
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from web.api.global_settings_schemas import (
    FileSystemBrowseResponse,
    FileSystemEntry,
)

router = APIRouter()


@router.get(
    "/fs-browse",
    response_model=FileSystemBrowseResponse,
)
def browse_filesystem(path: str = Query(default="/")):
    target = Path(path)
    if not target.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")

    resolved = target.resolve()
    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Not a directory: {resolved}",
        )

    entries: list[FileSystemEntry] = []
    try:
        for item in sorted(resolved.iterdir(), key=lambda p: p.name):
            try:
                st = item.stat()
            except OSError:
                continue
            is_dir = stat.S_ISDIR(st.st_mode)
            entries.append(
                FileSystemEntry(
                    name=item.name,
                    path=str(item),
                    is_dir=is_dir,
                    size_bytes=None if is_dir else st.st_size,
                )
            )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    dirs = [e for e in entries if e.is_dir]
    files = [e for e in entries if not e.is_dir]

    return FileSystemBrowseResponse(
        current_path=str(resolved),
        entries=dirs + files,
    )
