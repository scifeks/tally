"""XSStrike local wrapper for XSS-focused dynamic web application scanning.

Seeds are supplied via ``--seeds`` from the URL discovery pipeline (Katana,
Noir, or a user-provided endpoint file). When no seeds file is available,
XSStrike is skipped and a warning is logged.

Invocation
----------
::

    xsstrike --seeds <seeds_file> --crawl --skip -l <level>
        -t <threads> --timeout 15
        --file-log-level DEBUG --log-file <logfile>

``--crawl`` activates XSStrike's Photon crawler, which follows links from
each seed URL to discover additional pages and tests every parameter it
finds. ``-l`` controls the crawl depth.

Output
------
XSStrike writes structured log entries to ``--log-file``.  The parser in
``infrastructure.tools.parsers.xsstrike`` correlates consecutive VULN-level
line pairs::

    <timestamp> xsstrike - VULN - Vulnerable webpage: <url>
    <timestamp> xsstrike - VULN - Vector for <param>: <payload>

FuzzyWuzzy
----------
XSStrike uses ``fuzzywuzzy`` for response similarity analysis.  When
available it improves detection accuracy; XSStrike still runs without it
but with reduced effectiveness.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
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
            headers (dict[str, str] | None): Extra HTTP headers serialized
                as JSON and passed via ``--headers``.
            blind (bool): When True, add ``--blind`` to enable blind XSS
                payload injection during crawl.
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        seeds_file: str | None = str(raw["seeds_file"]) if "seeds_file" in raw else None
        log_file: str | None = str(raw["log_file"]) if "log_file" in raw else None
        _crawl_level = raw.get("crawl_level", 10)
        crawl_level = _crawl_level if isinstance(_crawl_level, int) else 10
        _headers = raw.get("headers")
        headers: dict[str, str] | None = (
            _headers if isinstance(_headers, dict) else None
        )
        blind: bool = bool(raw.get("blind", False))

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

        if blind:
            cmd.append("--blind")

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

        Phase 9: the seeds file is JIT-rebuilt from ``url_findings`` rows
        right before the scan runs. Returns an empty list (skipping
        XSStrike) when no rows exist for the repo.
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
        output_dir = paths.tool_output_dir("xsstrike")
        output_dir.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        log_file = str(output_dir / f"{repo.name}_{ts}.log")

        seeds_file, _oas3_path = jit_rebuild_artifacts(
            context.base_path, context.project_name, repo, url_finding_repo=url_repo
        )
        if not seeds_file or not Path(seeds_file).exists():
            logger.warning(
                "XSStrike: no URL inventory for %s; skipping. "
                "Run Katana, Noir, or configure an endpoint file to "
                "generate URL discovery output.",
                repo.name,
            )
            return []

        kwargs: dict[str, Any] = {
            "seeds_file": seeds_file,
            "log_file": log_file,
            "crawl_level": repo.xsstrike_crawl_level,
        }
        if repo.xsstrike_headers:
            kwargs["headers"] = dict(repo.xsstrike_headers)
        if context.tool_config.blind_xss_callback_url:
            kwargs["blind"] = True

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
