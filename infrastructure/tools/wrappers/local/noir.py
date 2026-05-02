"""OWASP Noir local wrapper for endpoint discovery via static analysis.

Invocation pattern
------------------
``noir -b <source_path> -f oas3 --no-log -o <output_file>``

The ``-o`` flag writes the OAS3 JSON report to a file on disk; Noir does not
write it to stdout.  This follows the same pattern as ``GitleaksLocalTool``:
``build_command`` stores the report path in ``self._last_report_path`` and
``parse_output`` reads from it.

The OAS3 file is not deleted after parsing because the URL-inventory
ingest handler reads it via ``output_files['oas3']``. The on-disk file
is the raw Noir output; vendor-path filtering is applied in the
application core (see ``application.url_inventory.providers
._oas3_to_findings.iter_oas3_rows``) at ingest time. This ensures vendor
URLs never enter ``url_findings`` and the rebuilt merged OAS3 (consumed by
ZAP, XSStrike, DalFox) inherits the filter.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.noir import (
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
            techs (list[str]): Noir tech identifiers to pass via ``-t``.
                When empty or absent, no ``-t`` flag is added.
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

        # Resolve to an absolute path because Noir may cd internally.
        output_file = str(Path(output_file).resolve())
        self._last_report_path = Path(output_file)

        raw_techs = kwargs.get("techs")
        techs: list[str] = list(raw_techs) if isinstance(raw_techs, list) else []

        cmd = [
            "noir",
            "-b",
            source_path,
            "-f",
            "oas3",
            "--no-log",
            "-o",
            output_file,
        ]

        if techs:
            cmd.extend(["-t", ",".join(techs)])

        ai_provider_url = kwargs.get("ai_provider_url")
        ai_model = kwargs.get("ai_model")
        if ai_provider_url and ai_model:
            cmd.extend(["--ai-provider", str(ai_provider_url)])
            cmd.extend(["--ai-model", str(ai_model)])
            ai_max_token = kwargs.get("ai_max_token")
            if ai_max_token is not None:
                cmd.extend(["--ai-max-token", str(ai_max_token)])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse Noir OAS3 output into structured endpoint data.

        Preference order:
        1. The report file written via ``-o`` (``self._last_report_path``).
        2. The stdout file saved by the executor (unusual, but safe fallback).
        3. The raw output string.

        Empty OAS3 files (zero paths) are deleted so the ingest handler
        does not import an empty spec.

        Vendor / dependency path filtering happens at the URL-inventory
        ingest boundary (``iter_oas3_rows``), not here. The wrapper's
        only job is to surface Noir's raw output.
        """
        try:
            if self._last_report_path is not None and self._last_report_path.exists():
                parsed = parse_noir_json(self._last_report_path)
            else:
                json_path = files.get("stdout")
                if json_path is not None and json_path.exists():
                    parsed = parse_noir_json(json_path)
                else:
                    parsed = parse_noir_json_string(output)

            if (
                not parsed.get("endpoints")
                and self._last_report_path is not None
                and self._last_report_path.exists()
            ):
                self._last_report_path.unlink()

            # Expose the OAS3 report path through ``output_files`` so the
            # URL inventory ingest handler can read it from ToolResult.
            if self._last_report_path is not None and self._last_report_path.exists():
                files["oas3"] = self._last_report_path

            return parsed
        finally:
            self._last_report_path = None
