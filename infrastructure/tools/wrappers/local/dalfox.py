"""DalFox local wrapper for XSS scanning of SPAs and JavaScript-heavy apps.

Invocation modes
----------------
The wrapper supports three URL seed modes, controlled by
``repo.dalfox_mode``:

DalFox has **no built-in crawler**.  Seeds must be provided externally;
this wrapper supports two modes:

**noir** (default)
    Seeds are generated from the most recent Noir OAS3 output for the
    repository.  Each OAS3 path is joined with ``base_url`` to produce a
    seeds file.  Falls back to ``crawl`` mode when no Noir output exists::

        dalfox file <seeds_file> --format json -o <output_file>
            --no-spinner --no-color --deep-domxss

**provided**
    Seeds are generated from ``repo.oas3_path`` (the user-supplied endpoint
    file already converted to OAS3).  Falls back to ``crawl`` mode when
    ``oas3_path`` is empty::

        dalfox file <seeds_file> --format json -o <output_file>
            --no-spinner --no-color --deep-domxss

Output
------
DalFox writes JSON to the output file specified via ``-o``.  The output is
an array of PoC objects with fields including Type, Param, Payload, PoC,
CWE, Severity, InjectType, Method, Evidence, and MessageStr.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.dalfox import (
    parse_dalfox_json,
    parse_dalfox_json_string,
)
from infrastructure.tools.version import get_tool_version
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
        return get_tool_version(self.command)

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
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        seeds_file: str | None = str(raw["seeds_file"]) if "seeds_file" in raw else None
        output_file: str | None = (
            str(raw["output_file"]) if "output_file" in raw else None
        )
        headers: dict[str, str] | None = raw.get("headers") or None  # type: ignore[assignment]

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
            ]
        )

        if headers:
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])

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

        Resolves the URL seed mode from ``repo.dalfox_mode`` and builds the
        appropriate kwargs.  Returns an empty list (skipping DalFox) when no
        seeds file can be built — e.g. Noir output is missing or oas3_path
        is empty.
        """
        assert context.repo is not None
        repo = context.repo
        base_url = repo.base_urls[0] if repo.base_urls else ""
        mode = (repo.dalfox_mode or "noir").lower()

        output_dir = (
            Path(context.base_path).resolve()
            / "projects"
            / context.project_name
            / "tool_outputs"
            / "dalfox"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_file = str(output_dir / f"{repo.name}_{ts}.json")

        kwargs: dict[str, Any] = {
            "output_file": output_file,
        }
        if repo.dalfox_headers:
            kwargs["headers"] = dict(repo.dalfox_headers)

        if mode == "noir":
            seeds_file = _build_seeds_from_noir(
                context.base_path,
                context.project_name,
                repo.name,
                base_url,
                output_dir,
                ts,
            )
            if seeds_file:
                kwargs["seeds_file"] = seeds_file
            else:
                logger.info(
                    "DalFox: no Noir output found for %s — skipping",
                    repo.name,
                )
                return []

        elif mode == "provided":
            oas3_path = repo.oas3_path or ""
            if oas3_path:
                seeds_file = _build_seeds_from_oas3(
                    Path(oas3_path), base_url, output_dir, ts
                )
                if seeds_file:
                    kwargs["seeds_file"] = seeds_file
                else:
                    logger.info(
                        "DalFox: could not extract seeds from oas3_path %r "
                        "for %s — skipping",
                        oas3_path,
                        repo.name,
                    )
                    return []
            else:
                logger.info(
                    "DalFox: mode='provided' but oas3_path is empty for %s — skipping",
                    repo.name,
                )
                return []

        else:
            logger.warning(
                "DalFox: unknown mode %r for %s — skipping",
                mode,
                repo.name,
            )
            return []

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]


# ---------------------------------------------------------------------------
# Seeds-file helpers
# ---------------------------------------------------------------------------


def _build_seeds_from_noir(
    base_path: str,
    project_name: str,
    repo_name: str,
    base_url: str,
    output_dir: Path,
    ts: str,
) -> str | None:
    """Locate the most recent Noir OAS3 file and write a seeds file from it.

    Returns the seeds file path on success, or ``None`` when no suitable
    Noir output exists.
    """
    noir_dir = Path(base_path) / "projects" / project_name / "tool_outputs" / "noir"
    if not noir_dir.exists():
        return None

    matches = sorted(noir_dir.glob(f"{repo_name}_*_oas3.json"))
    if not matches:
        return None

    candidate = matches[-1]
    try:
        with open(candidate, encoding="utf-8") as fh:
            data = json.load(fh)
        paths = list(data.get("paths", {}).keys())
        if not paths:
            return None
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    return _write_seeds_file(paths, base_url, output_dir, ts)


def _build_seeds_from_oas3(
    oas3_path: Path,
    base_url: str,
    output_dir: Path,
    ts: str,
) -> str | None:
    """Extract paths from an OAS3 file and write a seeds file.

    Returns the seeds file path on success, or ``None`` on error.
    """
    if not oas3_path.exists():
        return None
    try:
        with open(oas3_path, encoding="utf-8") as fh:
            data = json.load(fh)
        paths = list(data.get("paths", {}).keys())
        if not paths:
            return None
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    return _write_seeds_file(paths, base_url, output_dir, ts)


def _write_seeds_file(
    paths: list[str],
    base_url: str,
    output_dir: Path,
    ts: str,
) -> str | None:
    """Combine ``base_url`` + each path and write a seeds text file.

    Returns the seeds file path, or ``None`` when the path list is empty.
    """
    if not paths:
        return None

    base = base_url.rstrip("/")
    urls = [base + (p if p.startswith("/") else "/" + p) for p in paths]

    seeds_path = output_dir / f"seeds_{ts}.txt"
    seeds_path.write_text("\n".join(urls) + "\n", encoding="utf-8")
    return str(seeds_path)
