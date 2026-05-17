"""DalFox local wrapper for XSS scanning of SPAs and JavaScript-heavy apps.

DalFox has no built-in crawler; seeds must be provided externally. This
wrapper reads ``repo.merged_seeds_path``, the canonical deduplicated seeds
file produced by the URL discovery pipeline after Katana, Noir, and/or a
user-provided endpoint file run.

When ``merged_seeds_path`` is empty or missing, DalFox is skipped and a
warning is logged.

Invocation
----------
::

    dalfox file <seeds_file> --format json -o <output_file>
        --no-spinner --no-color --deep-domxss
        --remote-payloads portswigger,payloadbox

Output
------
DalFox writes JSON to the output file specified via ``-o``.  The output is
an array of PoC objects with fields including Type, Param, Payload, PoC,
CWE, Severity, InjectType, Method, Evidence, and MessageStr.
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.dalfox import (
    parse_dalfox_json,
    parse_dalfox_json_string,
)
from infrastructure.tools.wrappers.base.dalfox import BaseDalFoxTool

logger = logging.getLogger(__name__)


class DalFoxLocalTool(BaseDalFoxTool):
    """Concrete local wrapper for DalFox."""

    def __init__(self, config=None) -> None:
        self._dalfox_path: str = config.path if config is not None else "dalfox"
        # Set by build_command(); read by parse_output().
        self._last_output_path: Path | None = None

    @property
    def command(self) -> str:
        return "dalfox"

    def check_available(self) -> bool:
        return shutil.which("dalfox") is not None

    def get_version(self) -> str | None:
        """Run ``dalfox version`` (subcommand, not --version flag) and
        return the semver string, or ``None`` on failure."""
        import re
        import subprocess

        binary = shutil.which("dalfox")
        if binary is None:
            return None
        try:
            result = subprocess.run(
                [binary, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (result.stdout or result.stderr).strip()
            if not output:
                return None
            clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
            match = re.search(r"\d+\.\d+[\d.]*", clean)
            return match.group(0) if match else None
        except Exception:
            return None

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the DalFox argv list.

        Keyword Args:
            base_url (str): Base URL to scan.  Required when ``seeds_file``
                is not provided.
            seeds_file (str | None): Path to a seeds file (one URL per line).
                When provided, ``dalfox file`` subcommand is used instead of
                ``dalfox url``.
            output_file (str): Absolute path for the DalFox JSON output.
                Required.
            headers (dict[str, str] | None): Extra HTTP headers passed via
                ``-H "Key: Value"`` (one flag per header).
            blind_xss_callback (str | None): Blind XSS callback URL
                passed via ``-b``.
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        seeds_file: str | None = str(raw["seeds_file"]) if "seeds_file" in raw else None
        output_file: str | None = (
            str(raw["output_file"]) if "output_file" in raw else None
        )
        headers: dict[str, str] | None = raw.get("headers") or None  # type: ignore[assignment]
        blind_xss_callback: str | None = (
            str(raw["blind_xss_callback"]) if raw.get("blind_xss_callback") else None
        )

        if not base_url and not seeds_file:
            raise ValueError("Either base_url or seeds_file is required for dalfox")
        if not output_file:
            raise ValueError("output_file is required for dalfox")

        self._last_output_path = Path(str(output_file))

        cmd: list[str] = [self._dalfox_path]

        if seeds_file:
            cmd.extend(["file", str(seeds_file)])
        else:
            cmd.extend(["url", str(base_url)])

        cmd.extend(
            [
                "--format",
                "json",
                "-o",
                str(output_file),
                "--no-spinner",
                "--no-color",
                "--deep-domxss",
                "--skip-grepping",
                "--remote-payloads",
                "portswigger,payloadbox",
            ]
        )

        if headers:
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])

        if blind_xss_callback:
            cmd.extend(["-b", blind_xss_callback])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse DalFox JSON output into structured finding data."""
        try:
            if self._last_output_path is not None and self._last_output_path.exists():
                return parse_dalfox_json(self._last_output_path)
            stdout_path = files.get("stdout")
            if stdout_path is not None and stdout_path.exists():
                return parse_dalfox_json(stdout_path)
            return parse_dalfox_json_string(output)
        finally:
            self._last_output_path = None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for DalFox.

        Phase 9: the seeds file is JIT-rebuilt from ``url_findings`` rows
        right before the scan runs. Returns an empty list (skipping
        DalFox) when no rows exist for the repo.
        """
        from application.url_inventory.jit import jit_rebuild_artifacts
        from infrastructure.store.connection import ConnectionFactory
        from infrastructure.store.repositories.url_findings import (
            UrlFindingRepository,
        )

        assert context.repo is not None
        repo = context.repo

        paths = ProjectPaths.from_canonical(
            Path(context.base_path).resolve(), context.project_name
        )
        output_dir = paths.tool_output_dir("dalfox")
        output_dir.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_file = str(output_dir / f"{repo.name}_{ts}.json")

        seeds_file, _oas3_path = jit_rebuild_artifacts(
            context.base_path, context.project_name, repo, url_finding_repo=url_repo
        )
        if not seeds_file or not Path(seeds_file).exists():
            logger.warning(
                "DalFox: no URL inventory for %s; skipping. "
                "Run Katana, Noir, or configure an endpoint file to "
                "generate URL discovery output.",
                repo.name,
            )
            return []

        kwargs: dict[str, Any] = {
            "seeds_file": seeds_file,
            "output_file": output_file,
        }
        if repo.dalfox_headers:
            kwargs["headers"] = dict(repo.dalfox_headers)
        blind_url = context.tool_config.blind_xss_callback_url
        if blind_url:
            kwargs["blind_xss_callback"] = blind_url

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
