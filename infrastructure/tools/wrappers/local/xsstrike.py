"""XSStrike local wrapper for XSS-focused dynamic web application scanning.

Invocation modes
----------------
The wrapper supports three URL seed modes, controlled by
``repo.xsstrike_mode``.  XSStrike has no built-in URL crawler — all URLs
must be supplied from external discovery tools or a user-provided file.

**noir+katana** (default)
    Seeds are generated from the most recent Katana OAS3 output for the
    repository, with Noir OAS3 output as a fallback.  Each OAS3 path is
    joined with ``base_url`` to produce a seeds file.  Skips XSStrike when
    neither Katana nor Noir output exists::

        xsstrike --seeds <seeds_file> --crawl --skip -l <level>
            --path -e -t <threads> --timeout 15
            --file-log-level DEBUG --log-file <logfile>

**auto**
    Tries ``noir+katana`` seeds first; if neither is available but
    ``repo.oas3_path`` is set, falls back to the user-provided file.
    Skips XSStrike when no seeds can be produced.

**provided**
    Seeds are generated from ``repo.oas3_path`` (the user-supplied endpoint
    file already converted to OAS3).  Skips XSStrike when ``oas3_path`` is
    empty or yields no paths.

Note on ``--crawl``
-------------------
The ``--crawl`` flag passed to XSStrike controls DOM-level crawling of each
seed URL (following links within the page to find additional injection
points).  It is **not** related to URL enumeration and is always included
regardless of seed mode.

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
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.xsstrike import (
    parse_xsstrike_log,
    parse_xsstrike_log_string,
)
from infrastructure.tools.wrappers.base.xsstrike import BaseXSStrikeTool

logger = logging.getLogger(__name__)


def _recommended_thread_count() -> int:
    """Return a safe XSStrike thread count based on available CPUs.

    Caps at 8 to avoid hammering targets and triggering WAF rate limits.
    Floors at 2 so single-core environments still benefit from concurrency.
    """
    cpus = os.cpu_count() or 2
    return max(2, min(cpus, 8))


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
        """XSStrike has no ``--version`` flag; always returns ``None``."""
        return None

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the XSStrike argv list.

        Keyword Args:
            base_url (str): Base URL to scan.  Required when ``seeds_file``
                is not provided.
            seeds_file (str | None): Path to a seeds file (one URL per line).
                When provided, ``-u`` is omitted and ``--seeds`` is used.
            log_file (str): Absolute path for the XSStrike log output.
                Required.
            crawl_level (int): Passed as ``-l``. Controls crawl depth.
                Defaults to 10.
            headers (dict[str, str] | None): Extra HTTP headers serialised
                as JSON and passed via ``--headers``.
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        seeds_file: str | None = str(raw["seeds_file"]) if "seeds_file" in raw else None
        log_file: str | None = str(raw["log_file"]) if "log_file" in raw else None
        crawl_level: int = int(raw.get("crawl_level", 10))  # type: ignore[arg-type]
        headers: dict[str, str] | None = raw.get("headers") or None  # type: ignore[assignment]

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
                "-l",
                str(crawl_level),
                "--path",
                "-e",
                "-t",
                str(_recommended_thread_count()),
                "--timeout",
                "15",
                "--file-log-level",
                "DEBUG",
                "--log-file",
                str(log_file),
            ]
        )

        if headers:
            cmd.extend(["--headers", json.dumps(headers)])

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

        Resolves the URL seed mode from ``repo.xsstrike_mode`` and builds
        the appropriate kwargs.  Returns an empty list (skipping XSStrike)
        when no seeds can be produced — there is no fallback crawl mode.
        """
        assert context.repo is not None
        repo = context.repo
        base_url = repo.base_urls[0] if repo.base_urls else ""
        mode = (repo.xsstrike_mode or "noir+katana").lower()

        output_dir = (
            Path(context.base_path).resolve()
            / "projects"
            / context.project_name
            / "tool_outputs"
            / "xsstrike"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        log_file = str(output_dir / f"{repo.name}_{ts}.log")

        kwargs: dict[str, Any] = {
            "log_file": log_file,
            "crawl_level": repo.xsstrike_crawl_level,
        }
        if repo.xsstrike_headers:
            kwargs["headers"] = dict(repo.xsstrike_headers)

        if mode in ("noir+katana", "noir", "katana"):
            # "noir" and "katana" are legacy values — treat as "noir+katana".
            seeds_file = _build_seeds_from_katana(
                context.base_path,
                context.project_name,
                repo.name,
                base_url,
                output_dir,
                ts,
            )
            if not seeds_file:
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
                    "XSStrike: no Katana or Noir output found for %s — skipping",
                    repo.name,
                )
                return []

        elif mode == "auto":
            seeds_file = _build_seeds_from_katana(
                context.base_path,
                context.project_name,
                repo.name,
                base_url,
                output_dir,
                ts,
            )
            if not seeds_file:
                seeds_file = _build_seeds_from_noir(
                    context.base_path,
                    context.project_name,
                    repo.name,
                    base_url,
                    output_dir,
                    ts,
                )
            if not seeds_file:
                oas3_path = repo.oas3_path or ""
                if oas3_path:
                    seeds_file = _build_seeds_from_oas3(
                        Path(oas3_path), base_url, output_dir, ts
                    )
            if seeds_file:
                kwargs["seeds_file"] = seeds_file
            else:
                logger.info(
                    "XSStrike: no seeds available for %s (auto mode) — skipping",
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
                        "XSStrike: could not extract seeds from oas3_path %r "
                        "for %s — skipping",
                        oas3_path,
                        repo.name,
                    )
                    return []
            else:
                logger.info(
                    "XSStrike: mode='provided' but oas3_path is empty for %s "
                    "— skipping",
                    repo.name,
                )
                return []

        else:
            logger.warning(
                "XSStrike: unknown mode %r for %s — skipping",
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


def _build_seeds_from_katana(
    base_path: str,
    project_name: str,
    repo_name: str,
    base_url: str,
    output_dir: Path,
    ts: str,
) -> str | None:
    """Locate the most recent Katana OAS3 file and write a seeds file from it.

    Returns the seeds file path on success, or ``None`` when no suitable
    Katana output exists.
    """
    katana_dir = Path(base_path) / "projects" / project_name / "tool_outputs" / "katana"
    if not katana_dir.exists():
        return None

    matches = sorted(katana_dir.glob(f"{repo_name}_*_oas3.json"))
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
