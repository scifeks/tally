"""Docker wrapper for XSStrike XSS-focused dynamic web application scanning.

XSStrike is invoked via ``docker exec`` on an already-running container that
has XSStrike (and its ``fuzzywuzzy`` dependency) installed.

Output
------
Because the container filesystem is not directly accessible from the host,
this wrapper uses ``--console-log-level DEBUG`` instead of ``--log-file``.
XSStrike writes finding lines to stderr; the executor captures them in the
``stderr`` output file.  ``parse_output`` reads the stderr file first, then
falls back to the stdout file and the raw combined output string.

The same ``parse_xsstrike_log_string`` parser handles both the file-log
format (used by the local wrapper) and the console-log format (used here),
because the VULN-line patterns are identical after ANSI codes are stripped.

Seeds
-----
Reads ``repo.merged_seeds_path``, the canonical deduplicated seeds file
produced by the URL discovery pipeline after Katana, Noir, and/or a
user-provided endpoint file run. The seeds file must be accessible inside
the container; mount the tally project's ``tool_outputs`` directory as a
volume (e.g. ``-v /path/to/tally_data:/tally_data``). When no seeds file
is available, XSStrike is skipped and a warning is logged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.xsstrike import parse_xsstrike_log_string
from infrastructure.tools.wrappers.base.xsstrike import BaseXSStrikeTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec
from infrastructure.tools.wrappers.local.xsstrike import _recommended_thread_count

logger = logging.getLogger(__name__)


class XSSTrikeDockerTool(BaseXSStrikeTool):
    """Docker wrapper for XSStrike."""

    def __init__(self, config: Any) -> None:
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
        """Build docker exec argv for XSStrike.

        Keyword Args:
            base_url (str): Base URL to scan.  Required when ``seeds_file``
                is not provided.
            seeds_file (str | None): Container-internal path to a seeds file.
                When provided, ``-u`` is omitted and ``--seeds`` is used.
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
        _crawl_level = raw.get("crawl_level", 10)
        crawl_level = _crawl_level if isinstance(_crawl_level, int) else 10
        _headers = raw.get("headers")
        headers: dict[str, str] | None = (
            _headers if isinstance(_headers, dict) else None
        )
        blind: bool = bool(raw.get("blind", False))

        if not base_url and not seeds_file:
            raise ValueError("Either base_url or seeds_file is required for xsstrike")

        tool_args: list[str] = []

        if seeds_file:
            tool_args.extend(["--seeds", str(seeds_file)])
        else:
            tool_args.extend(["-u", str(base_url)])

        tool_args.extend(
            [
                "--crawl",
                "--skip",
                "-l",
                str(crawl_level),
                "-t",
                str(_recommended_thread_count()),
                "--timeout",
                "15",
                "--console-log-level",
                "DEBUG",
            ]
        )

        if headers:
            tool_args.extend(["--headers", json.dumps(headers)])

        if blind:
            tool_args.append("--blind")

        return build_docker_exec(self._container_name, self._tool_path, tool_args)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse XSStrike console output captured from docker exec stderr."""
        stderr_path = files.get("stderr")
        if stderr_path is not None and stderr_path.exists():
            return parse_xsstrike_log_string(
                stderr_path.read_text(encoding="utf-8", errors="replace")
            )
        stdout_path = files.get("stdout")
        if stdout_path is not None and stdout_path.exists():
            return parse_xsstrike_log_string(
                stdout_path.read_text(encoding="utf-8", errors="replace")
            )
        return parse_xsstrike_log_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for XSStrike.

        Phase 9: the seeds file is JIT-rebuilt from ``url_findings`` rows
        right before the scan runs. Returns an empty list (skipping
        XSStrike) when no rows exist. The seeds file must be accessible
        inside the container; the relevant directory must be
        volume-mounted.
        """
        from application.url_inventory.jit import jit_rebuild_artifacts
        from infrastructure.store.connection import ConnectionFactory
        from infrastructure.store.repositories.url_findings import (
            UrlFindingRepository,
        )

        assert context.repo is not None
        repo = context.repo

        paths = ProjectPaths.from_canonical(context.base_path, context.project_name)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

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
