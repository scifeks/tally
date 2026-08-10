"""Apidocs local wrapper for agentic endpoint discovery.

Dispatches the 4-stage pipeline via claude -p invocations. Each
stage runs as a separate ExecutionPass with its own subprocess.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.apidocs import (
    parse_apidocs_output,
)
from infrastructure.tools.wrappers.base.apidocs import (
    _APIDOCS_PKG,
    BaseApidocsTool,
)

_ENRICH_SCRIPT = _APIDOCS_PKG / "enrich_driver.sh"


class ApidocsLocalTool(BaseApidocsTool):
    """Concrete local wrapper for the apidocs pipeline."""

    def __init__(self, config=None) -> None:
        self._current_stage = ""

    @property
    def command(self) -> str:
        return "claude"

    def check_available(self) -> bool:
        return shutil.which("claude") is not None

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs: object) -> list[str]:
        stage = str(kwargs["stage"])
        self._current_stage = stage
        repo_path = str(kwargs["repo_path"])

        if stage == "recon":
            return [
                "claude",
                "-p",
                "--agent",
                "apidocs-recon",
                "Run apidocs recon on this repository",
            ]
        if stage == "discovery":
            return [
                "claude",
                "-p",
                "--agent",
                "apidocs-discovery",
                ("Run apidocs discovery on this repository"),
            ]
        if stage == "enrich":
            return [
                "bash",
                str(_ENRICH_SCRIPT),
                "--repo",
                repo_path,
            ]
        if stage == "assemble":
            return [
                "claude",
                "-p",
                (
                    "Use the apidocs-assemble skill to"
                    " assemble the OpenAPI spec from the"
                    " enrichment fragments in apidocs/"
                ),
            ]
        raise ValueError(f"Unknown apidocs stage: {stage!r}")

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        if self._current_stage != "assemble":
            return {
                "stage": self._current_stage,
                "endpoints": [],
            }
        return parse_apidocs_output(
            repo_path=getattr(self, "_repo_path", ""),
            output_file=getattr(self, "_output_file", ""),
            files=files,
        )
