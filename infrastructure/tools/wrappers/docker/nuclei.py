"""Nuclei docker wrapper for template-based vulnerability scanning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.nuclei import (
    parse_nuclei_json,
    parse_nuclei_json_string,
)
from infrastructure.tools.wrappers.base.nuclei import BaseNucleiTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class NucleiDockerTool(BaseNucleiTool):
    """Docker execution strategy for nuclei."""

    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs: object) -> list[str]:
        """Build docker exec argv for nuclei."""
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        urls_file: str | None = str(raw["urls_file"]) if "urls_file" in raw else None
        custom_template_dir: str | None = (
            str(raw["custom_template_dir"]) if "custom_template_dir" in raw else None
        )
        default_template_dir: str | None = (
            str(raw["default_template_dir"]) if "default_template_dir" in raw else None
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

        tool_args: list[str] = []

        if urls_file:
            tool_args.extend(["-list", str(urls_file)])
        else:
            tool_args.extend(["-target", str(base_url)])

        if pass_type == "automatic":
            tool_args.extend(["-as", "-severity", "critical,high,medium"])
        else:
            tool_args.extend(["-dast", "-severity", "critical,high"])

        tool_args.extend(["-json-export", str(output_file)])

        if custom_template_dir and default_template_dir:
            tool_args.extend(["-t", f"{default_template_dir},{custom_template_dir}"])
        elif custom_template_dir:
            tool_args.extend(["-t", str(custom_template_dir)])
        elif default_template_dir:
            tool_args.extend(["-t", str(default_template_dir)])

        return build_docker_exec(self._container_name, self._tool_path, tool_args)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse nuclei output from stdout."""
        stdout_path = files.get("stdout")
        if stdout_path is not None and stdout_path.exists():
            return parse_nuclei_json(stdout_path)
        return parse_nuclei_json_string(output)
