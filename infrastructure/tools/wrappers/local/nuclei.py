"""Nuclei local wrapper for template-based vulnerability scanning."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.nuclei import (
    parse_nuclei_json,
    parse_nuclei_json_string,
)
from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.nuclei import BaseNucleiTool


class NucleiLocalTool(BaseNucleiTool):
    """Concrete local wrapper for Nuclei."""

    def __init__(self, config=None) -> None:
        self._nuclei_path: str = config.path if config is not None else "nuclei"
        self._last_output_path: Path | None = None

    @property
    def command(self) -> str:
        return "nuclei"

    def check_available(self) -> bool:
        return shutil.which("nuclei") is not None

    def get_version(self) -> str | None:
        return get_tool_version("nuclei")

    def build_command(self, **kwargs: object) -> list[str]:
        """Build nuclei command argv."""
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        urls_file: str | None = str(raw["urls_file"]) if "urls_file" in raw else None
        custom_template_dir: str | None = (
            str(raw["custom_template_dir"]) if "custom_template_dir" in raw else None
        )
        pass_type: str | None = str(raw["pass_type"]) if "pass_type" in raw else None
        output_file: str | None = (
            str(raw["output_file"]) if "output_file" in raw else None
        )

        if not base_url and not urls_file:
            raise ValueError("Either base_url or urls_file is required for nuclei")
        if not output_file:
            raise ValueError("output_file is required for nuclei")
        if not pass_type:
            raise ValueError("pass_type is required for nuclei")
        if pass_type not in ("automatic", "dast"):
            raise ValueError(
                f"pass_type must be 'automatic' or 'dast', got {pass_type!r}"
            )

        self._last_output_path = Path(str(output_file))

        cmd: list[str] = [self._nuclei_path]

        if urls_file:
            cmd.extend(["-list", str(urls_file)])
        else:
            cmd.extend(["-target", str(base_url)])

        if pass_type == "automatic":
            cmd.extend(["-as", "-severity", "critical,high,medium"])
        else:
            cmd.extend(["-dast", "-severity", "critical,high"])

        cmd.extend(["-json-export", str(output_file)])

        if custom_template_dir:
            cmd.extend(["-t", str(custom_template_dir)])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse nuclei output, preferring -json-export file."""
        try:
            if self._last_output_path is not None and self._last_output_path.exists():
                return parse_nuclei_json(self._last_output_path)
            stdout_path = files.get("stdout")
            if stdout_path is not None and stdout_path.exists():
                return parse_nuclei_json(stdout_path)
            return parse_nuclei_json_string(output)
        finally:
            self._last_output_path = None
