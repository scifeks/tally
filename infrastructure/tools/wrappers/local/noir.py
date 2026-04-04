"""OWASP Noir local wrapper — endpoint discovery via static analysis.

Invocation pattern
------------------
``noir -b <source_path> -f oas3 --no-log -o <output_file>``

The ``-o`` flag writes the OAS3 JSON report to a file on disk; Noir does not
write it to stdout.  This follows the same pattern as ``GitleaksLocalTool``:
``build_command`` stores the report path in ``self._last_report_path`` and
``parse_output`` reads from it.

The OAS3 file is **not** deleted after parsing because ZAP consumes it in the
next pipeline stage via its ``-openapifile`` flag (see ``ZAPLocalTool``).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.noir_parser import (
    parse_noir_json,
    parse_noir_json_string,
)
from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.noir import BaseNoirTool


class NoirLocalTool(BaseNoirTool):
    """Concrete local wrapper for the OWASP Noir binary."""

    def __init__(self, config=None) -> None:
        # Stores the OAS3 output path between build_command and parse_output.
        self._last_report_path: Path | None = None

    @property
    def command(self) -> str:
        return "noir"

    def check_available(self) -> bool:
        return shutil.which("noir") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the Noir argv list.

        Keyword Args:
            source_path (str): Path to the source code to scan.  Required.
                Must be an existing directory.
            output_file (str): Absolute path for the OAS3 JSON output.  Required.
                The directory must already exist (created by
                ``build_execution_passes``).
        """
        source_path: str | None = (
            str(kwargs["source_path"]) if "source_path" in kwargs else None
        )
        if not source_path:
            raise ValueError("source_path is required for noir")
        if not Path(source_path).exists():
            raise ValueError(f"Source path does not exist: {source_path!r}")

        output_file: str | None = (
            str(kwargs["output_file"]) if "output_file" in kwargs else None
        )
        if not output_file:
            raise ValueError("output_file is required for noir")

        # Resolve to an absolute path — Noir may cd internally.
        output_file = str(Path(output_file).resolve())
        self._last_report_path = Path(output_file)

        return [
            "noir",
            "-b",
            source_path,
            "-f",
            "oas3",
            "--no-log",
            "-o",
            output_file,
        ]

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse Noir OAS3 output into structured endpoint data.

        Preference order:
        1. The report file written via ``-o`` (``self._last_report_path``).
        2. The stdout file saved by the executor (unusual, but safe fallback).
        3. The raw output string.

        The OAS3 file is intentionally NOT removed after parsing — ZAP reads
        it in the subsequent pipeline stage.
        """
        try:
            if self._last_report_path is not None and self._last_report_path.exists():
                return parse_noir_json(self._last_report_path)
            json_path = files.get("stdout")
            if json_path is not None and json_path.exists():
                return parse_noir_json(json_path)
            return parse_noir_json_string(output)
        finally:
            # Clear the instance reference; the file on disk is preserved.
            self._last_report_path = None
