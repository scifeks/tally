"""Local wrapper for tree-sitter SAST tool."""

import sys
from pathlib import Path
from typing import Any

from ...base import ToolWrapper
from ..base.tree_sitter import BaseTreeSitterTool


class TreeSitterLocalTool(BaseTreeSitterTool, ToolWrapper):
    def __init__(self, config: object = None) -> None:
        pass  # no binary config needed

    @property
    def command(self) -> str:
        return sys.executable

    def check_available(self) -> bool:
        import importlib.util

        return (
            importlib.util.find_spec("tree_sitter") is not None
            and importlib.util.find_spec("tree_sitter_language_pack") is not None
        )

    def build_command(self, **kwargs: Any) -> list[str]:
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for tree-sitter")
        runner = (
            Path(__file__).resolve().parent.parent.parent
            / "runners"
            / "tree_sitter_runner.py"
        )
        return [sys.executable, str(runner), repo_path, "--format", "json"]

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        from core.tools.parsers.tree_sitter_parser import (
            parse_tree_sitter_json,
            parse_tree_sitter_json_string,
        )

        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_tree_sitter_json(json_path)
        return parse_tree_sitter_json_string(output)
