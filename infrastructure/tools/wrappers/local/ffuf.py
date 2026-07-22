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
        self._last_output_path: Path | None = None

    @property
    def command(self) -> str:
        return "ffuf"

    def check_available(self) -> bool:
        return shutil.which("ffuf") is not None

    def get_version(self) -> str | None:
        return get_tool_version("ffuf")

    def build_command(self, **kwargs: object) -> list[str]:
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        wordlist: str | None = str(raw["wordlist"]) if "wordlist" in raw else None
        output_file: str | None = (
            str(raw["output_file"]) if "output_file" in raw else None
        )

        if not base_url:
            raise ValueError("base_url is required for ffuf")
        if not wordlist:
            raise ValueError("wordlist is required for ffuf")
        if not output_file:
            raise ValueError("output_file is required for ffuf")

        self._last_output_path = Path(str(output_file))

        target_url = base_url.rstrip("/") + "/FUZZ"

        cmd: list[str] = [
            self._ffuf_path,
            "-u",
            target_url,
            "-w",
            wordlist,
            "-of",
            "json",
            "-o",
            output_file,
            "-mc",
            "200,201,301,302,307,401,403,405,500",
            "-s",
        ]

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        try:
            if self._last_output_path is not None and self._last_output_path.exists():
                return parse_ffuf_json(self._last_output_path)
            stdout_path = files.get("stdout")
            if stdout_path is not None and stdout_path.exists():
                return parse_ffuf_json(stdout_path)
            return parse_ffuf_json_string(output)
        finally:
            self._last_output_path = None
