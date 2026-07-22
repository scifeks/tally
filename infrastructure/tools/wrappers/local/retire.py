"""Retire.js wrapper for vulnerable JavaScript library detection (SCA)."""

from __future__ import annotations

import shutil
from pathlib import Path

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.retire import BaseRetireTool


class RetireLocalTool(BaseRetireTool):
    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "retire"

    def check_available(self) -> bool:
        return shutil.which("retire") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for retire")
        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")

        return [
            "retire",
            "--path",
            repo_path,
            "--outputformat",
            "json",
            "--exitwith",
            "0",
        ]
