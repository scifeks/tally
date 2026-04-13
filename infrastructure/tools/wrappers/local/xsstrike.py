"""XSStrike local wrapper for XSS-focused dynamic web application scanning.

Invocation modes
----------------
The wrapper supports three URL seed modes, controlled by
``repo.xsstrike_mode``:

**crawl** (default)
    XSStrike spiders from ``base_url`` directly::

        xsstrike -u <base_url> --crawl --skip
            --file-log-level DEBUG --log-file <logfile>

**noir**
    Seeds are generated from the most recent Noir OAS3 output for the
    repository.  Each OAS3 path is joined with ``base_url`` to produce a
    seeds file.  Falls back to ``crawl`` mode when no Noir output exists::

        xsstrike --seeds <seeds_file> --crawl --skip
            --file-log-level DEBUG --log-file <logfile>

**provided**
    Seeds are generated from ``repo.oas3_path`` (the user-supplied endpoint
    file already converted to OAS3).  Falls back to ``crawl`` mode when
    ``oas3_path`` is empty::

        xsstrike --seeds <seeds_file> --crawl --skip
            --file-log-level DEBUG --log-file <logfile>

Output
------
XSStrike writes structured log entries to ``--log-file``.  The parser in
``infrastructure.tools.parsers.xsstrike`` correlates consecutive VULN-level
line pairs::

    <timestamp> xsstrike - VULN - Vulnerable webpage: <url>
    <timestamp> xsstrike - VULN - Vector for <param>: <payload>

FuzzyWuzzy
----------
XSStrike uses ``fuzzywuzzy`` (installed as a tally dependency) for response
similarity analysis.  When available it improves detection accuracy; XSStrike
still runs without it but with reduced effectiveness.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.xsstrike import (
    parse_xsstrike_log,
    parse_xsstrike_log_string,
)
from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.xsstrike import BaseXSStrikeTool

logger = logging.getLogger(__name__)


class XSSTrikeLocalTool(BaseXSStrikeTool):
    """Concrete local wrapper for XSStrike."""

    def __init__(self, config=None) -> None:
        self._xsstrike_path: str = config.path if config is not None else "xsstrike"
        # Set by build_command(); read by parse_output().
        self._last_log_path: Path | None = None

    @property
    def command(self) -> str:
        return "xsstrike"

    def check_available(self) -> bool:
        return shutil.which("xsstrike") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the XSStrike argv list.

        Keyword Args:
            base_url (str): Base URL to scan.  Required when ``seeds_file``
                is not provided.
            seeds_file (str | None): Path to a seeds file (one URL per line).
                When provided, ``-u`` is omitted and ``--seeds`` is used.
            log_file (str): Absolute path for the XSStrike log output.
                Required.
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        seeds_file: str | None = str(raw["seeds_file"]) if "seeds_file" in raw else None
        log_file: str | None = str(raw["log_file"]) if "log_file" in raw else None

        if not base_url and not seeds_file:
            raise ValueError("Either base_url or seeds_file is required for xsstrike")
        if not log_file:
            raise ValueError("log_file is required for xsstrike")

        self._last_log_path = Path(str(log_file))

        cmd: list[str] = [self._xsstrike_path]

        if seeds_file:
            cmd.extend(["--seeds", str(seeds_file)])
        else:
            cmd.extend(["-u", str(base_url)])

        cmd.extend(
            [
                "--crawl",
                "--skip",
                "--file-log-level",
                "DEBUG",
                "--log-file",
                str(log_file),
            ]
        )
        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse XSStrike log output into structured finding data."""
        try:
            if self._last_log_path is not None and self._last_log_path.exists():
                return parse_xsstrike_log(self._last_log_path)
            stdout_path = files.get("stdout")
            if stdout_path is not None and stdout_path.exists():
                return parse_xsstrike_log(stdout_path)
            return parse_xsstrike_log_string(output)
        finally:
            self._last_log_path = None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for XSStrike.

        Resolves the URL seed mode from ``repo.xsstrike_mode`` and builds the
        appropriate kwargs.  Falls back to crawl mode when seeds cannot be
        generated (e.g. Noir output missing, oas3_path empty).
        """
        assert context.repo is not None
        repo = context.repo
        base_url = repo.base_urls[0] if repo.base_urls else ""
        mode = (repo.xsstrike_mode or "crawl").lower()

        output_dir = (
            Path(context.base_path)
            / "projects"
            / context.project_name
            / "tool_outputs"
            / "xsstrike"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        log_file = str(output_dir / f"{repo.name}_{ts}.log")

        kwargs: dict[str, Any] = {"log_file": log_file}

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
                    "XSStrike: no Noir output found for %s — falling back to "
                    "crawl mode",
                    repo.name,
                )
                kwargs["base_url"] = base_url

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
                        "XSStrike: could not extract seeds from oas3_path %r "
                        "for %s — falling back to crawl mode",
                        oas3_path,
                        repo.name,
                    )
                    kwargs["base_url"] = base_url
            else:
                logger.info(
                    "XSStrike: mode='provided' but oas3_path is empty for %s "
                    "— falling back to crawl mode",
                    repo.name,
                )
                kwargs["base_url"] = base_url

        else:
            # crawl mode (default)
            kwargs["base_url"] = base_url

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
