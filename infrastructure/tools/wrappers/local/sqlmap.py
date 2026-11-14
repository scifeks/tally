"""sqlmap local wrapper for SQL injection scanning.

Seeds are supplied via ``-m`` from the URL discovery pipeline (Katana,
Noir, or a user-provided endpoint file).  Only URLs with query
parameters are tested; clean paths are filtered out.  When no
parameterized URLs are available, sqlmap is skipped.

Invocation
----------
::

    sqlmap -m <seeds_file> --batch --level <level> --risk <risk>
        --output-dir <output_dir> --flush-session
        --disable-coloring

Output
------
sqlmap writes injection results to stdout as structured blocks
delimited by ``---`` markers.  The parser in
``infrastructure.tools.parsers.sqlmap`` extracts injectable
parameters, techniques, and DBMS info from these blocks.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.project_paths import ProjectPaths
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.sqlmap import (
    parse_sqlmap_output_string,
)
from infrastructure.tools.wrappers.base.sqlmap import (
    BaseSqlmapTool,
)

logger = logging.getLogger(__name__)


def _has_query_params(url: str) -> bool:
    return bool(urlparse(url).query)


def _write_parameterized_urls(seeds_path: Path, output_dir: Path) -> Path | None:
    """Filter *seeds_path* to parameterized URLs only.

    Returns path to the filtered file, or None if no
    parameterized URLs remain.
    """
    try:
        lines = seeds_path.read_text("utf-8").splitlines()
    except OSError:
        return None

    parameterized = [
        line.strip()
        for line in lines
        if line.strip() and _has_query_params(line.strip())
    ]
    if not parameterized:
        return None

    filtered = output_dir / "seeds_parameterized.txt"
    filtered.write_text("\n".join(parameterized) + "\n", encoding="utf-8")
    return filtered


class SqlmapLocalTool(BaseSqlmapTool):
    """Concrete local wrapper for sqlmap."""

    def __init__(self, config=None) -> None:
        self._sqlmap_path: str = config.path if config is not None else "sqlmap"

    @property
    def command(self) -> str:
        return "sqlmap"

    def check_available(self) -> bool:
        return shutil.which("sqlmap") is not None

    def get_version(self) -> str | None:
        try:
            proc = subprocess.run(
                [self._sqlmap_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the sqlmap argv list.

        Keyword Args:
            seeds_file (str): Path to filtered seeds file (one
                parameterized URL per line). Required.
            output_dir (str): Directory for sqlmap session output.
                Required.
            level (int): Detection level (1-5). Defaults to 1.
            risk (int): Risk level (1-3). Defaults to 1.
            headers (dict[str, str] | None): Extra HTTP headers as
                {name: value}. Passed via --header flag.
            tamper (str): Comma-separated tamper script names for WAF
                evasion (e.g., 'space2comment,between').
        """
        raw = kwargs or {}
        seeds_file = str(raw["seeds_file"]) if "seeds_file" in raw else None
        output_dir = str(raw["output_dir"]) if "output_dir" in raw else None
        _level = raw.get("level", 1)
        level = _level if isinstance(_level, int) else 1
        _risk = raw.get("risk", 1)
        risk = _risk if isinstance(_risk, int) else 1
        _headers = raw.get("headers")
        headers: dict[str, str] | None = (
            _headers if isinstance(_headers, dict) else None
        )
        tamper: str = str(raw.get("tamper", ""))

        if not seeds_file:
            raise ValueError("seeds_file is required for sqlmap")
        if not output_dir:
            raise ValueError("output_dir is required for sqlmap")

        cmd: list[str] = [
            self._sqlmap_path,
            "-m",
            str(seeds_file),
            "--batch",
            "--level",
            str(level),
            "--risk",
            str(risk),
            "--output-dir",
            str(output_dir),
            "--flush-session",
            "--disable-coloring",
            "--forms",
        ]

        if headers:
            for name, value in headers.items():
                cmd.extend(["--header", f"{name}: {value}"])

        if tamper:
            cmd.extend(["--tamper", tamper])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        return parse_sqlmap_output_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for sqlmap.

        Seeds are JIT-rebuilt from ``url_findings`` rows, then
        filtered to parameterized URLs only.  Returns an empty
        list (skipping sqlmap) when no parameterized URLs exist.
        """
        from application.url_inventory.jit import (
            jit_rebuild_artifacts,
        )
        from infrastructure.store.connection import (
            ConnectionFactory,
        )
        from infrastructure.store.repositories.url_findings import (
            UrlFindingRepository,
        )

        assert context.repo is not None
        repo = context.repo

        paths = ProjectPaths.from_canonical(
            Path(context.base_path).resolve(),
            context.project_name,
        )
        output_dir = paths.tool_output_dir("sqlmap")
        output_dir.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

        seeds_file, _oas3_path = jit_rebuild_artifacts(
            context.base_path,
            context.project_name,
            repo,
            url_finding_repo=url_repo,
        )
        if not seeds_file or not Path(seeds_file).exists():
            logger.warning(
                "sqlmap: no URL inventory for %s; skipping. "
                "sqlmap needs parameterized URLs (?key=value) "
                "from URL discovery. Run Katana or Noir first, "
                "or supply an endpoint file with query "
                "parameters.",
                repo.name,
            )
            return []

        filtered = _write_parameterized_urls(Path(seeds_file), output_dir)
        if not filtered:
            logger.warning(
                "sqlmap: no parameterized URLs found for "
                "%s; skipping. sqlmap requires URLs with "
                "query parameters to test.",
                repo.name,
            )
            return []

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        scan_output_dir = str(output_dir / f"{repo.name}_{ts}")

        from infrastructure.tools.wrappers.utils.auth_login import (
            build_tool_headers,
        )

        kwargs: dict[str, Any] = {
            "seeds_file": str(filtered),
            "output_dir": scan_output_dir,
            "level": repo.sqlmap_level,
            "risk": repo.sqlmap_risk,
        }
        headers = build_tool_headers(repo.auth, repo.sqlmap_headers)
        if headers:
            kwargs["headers"] = headers
        if repo.sqlmap_tamper:
            kwargs["tamper"] = repo.sqlmap_tamper

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
