"""FFuf local wrapper for web fuzzing."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.ffuf import (
    parse_ffuf_json,
    parse_ffuf_json_string,
)
from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.ffuf import BaseFFufTool

logger = logging.getLogger(__name__)


class FFufLocalTool(BaseFFufTool):
    def __init__(self, config=None) -> None:
        self._ffuf_path: str = config.path if config is not None else "ffuf"

    @property
    def command(self) -> str:
        return "ffuf"

    def check_available(self) -> bool:
        return shutil.which("ffuf") is not None

    def get_version(self) -> str | None:
        return get_tool_version("ffuf")

    def build_command(self, **kwargs: object) -> list[str]:
        raw = kwargs or {}
        wordlist: str | None = str(raw["wordlist"]) if "wordlist" in raw else None

        if not wordlist:
            raise ValueError("wordlist is required for ffuf")

        cmd: list[str] = [
            self._ffuf_path,
            "-w",
            wordlist,
        ]

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        tool_output = files.get("tool_output")
        if tool_output is not None and tool_output.exists():
            return parse_ffuf_json(tool_output)
        stdout_path = files.get("stdout")
        if stdout_path is not None and stdout_path.exists():
            return parse_ffuf_json(stdout_path)
        return parse_ffuf_json_string(output)
