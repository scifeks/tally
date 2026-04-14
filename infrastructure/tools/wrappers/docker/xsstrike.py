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

Seeds mode
----------
For ``noir`` and ``provided`` modes the seeds file must be accessible inside
the container.  Mount the tally project's ``tool_outputs`` directory as a
volume (e.g. ``-v /path/to/tally_data:/tally_data``) and configure
``container.tool_path`` and paths accordingly.  For simple ``crawl`` mode no
volume mount is required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.xsstrike import parse_xsstrike_log_string
from infrastructure.tools.wrappers.base.xsstrike import BaseXSStrikeTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec
from infrastructure.tools.wrappers.local.xsstrike import _recommended_thread_count


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
            headers (dict[str, str] | None): Extra HTTP headers serialised
                as JSON and passed via ``--headers``.
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        seeds_file: str | None = str(raw["seeds_file"]) if "seeds_file" in raw else None
        crawl_level: int = int(raw.get("crawl_level", 10))  # type: ignore[arg-type]
        headers: dict[str, str] | None = raw.get("headers") or None  # type: ignore[assignment]

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
                "--path",
                "-e",
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

        Builds kwargs from ``repo.xsstrike_mode``.  Seeds files for ``noir``
        and ``provided`` modes must be accessible inside the container; this
        wrapper passes the same host-side paths as the local wrapper — ensure
        the relevant directory is volume-mounted.
        """
        assert context.repo is not None
        repo = context.repo
        base_url = repo.base_urls[0] if repo.base_urls else ""
        mode = (repo.xsstrike_mode or "crawl").lower()

        kwargs: dict[str, Any] = {
            "crawl_level": repo.xsstrike_crawl_level,
        }
        if repo.xsstrike_headers:
            kwargs["headers"] = dict(repo.xsstrike_headers)

        if mode == "noir":
            from infrastructure.tools.wrappers.local.xsstrike import (
                _build_seeds_from_noir,
            )

            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            output_dir = (
                Path(context.base_path)
                / "projects"
                / context.project_name
                / "tool_outputs"
                / "xsstrike"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
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
                kwargs["base_url"] = base_url

        elif mode == "provided":
            from infrastructure.tools.wrappers.local.xsstrike import (
                _build_seeds_from_oas3,
            )

            oas3_path = repo.oas3_path or ""
            if oas3_path:
                ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                output_dir = (
                    Path(context.base_path)
                    / "projects"
                    / context.project_name
                    / "tool_outputs"
                    / "xsstrike"
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                seeds_file = _build_seeds_from_oas3(
                    Path(oas3_path), base_url, output_dir, ts
                )
                if seeds_file:
                    kwargs["seeds_file"] = seeds_file
                else:
                    kwargs["base_url"] = base_url
            else:
                kwargs["base_url"] = base_url

        else:
            kwargs["base_url"] = base_url

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
