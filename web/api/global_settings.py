"""Global settings API: tool config and filesystem browsing."""

from __future__ import annotations

import logging
import stat
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from core.config.manager import ConfigManager
from web.api.global_settings_schemas import (
    FileSystemBrowseResponse,
    FileSystemEntry,
    ToolSettingsResponse,
    UpdateToolSettingsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/tool-config",
    response_model=ToolSettingsResponse,
)
def get_tool_settings(request: Request):
    base_path: str = request.app.state.base_path
    cm = ConfigManager(base_path)
    return ToolSettingsResponse(
        ffuf_wordlist_paths=cm.global_config.ffuf_wordlist_paths,
    )


@router.put(
    "/tool-config",
    response_model=ToolSettingsResponse,
)
def update_tool_settings(
    request: Request,
    body: UpdateToolSettingsRequest,
):
    base_path: str = request.app.state.base_path
    cm = ConfigManager(base_path)
    with cm.locked_global_config():
        gc = cm.load_global_config()
        data = gc.model_dump()
        data["ffuf_wordlist_paths"] = body.ffuf_wordlist_paths
        updated = type(gc)(**data)
        cm.save_global_config(updated)

    return ToolSettingsResponse(
        ffuf_wordlist_paths=updated.ffuf_wordlist_paths,
    )


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
