"""graphql-cop local wrapper for GraphQL security auditing.

graphql-cop is a Python script (not a pip package) that takes a
single endpoint URL and checks for 12 vulnerability classes. The
commands.json ``path`` field points to the script location.

Output goes to stdout (``-o json`` sets the format, not an output
file). This wrapper stores the target URL as instance state so
``parse_output`` can inject it into the parsed data for the
handler to read.

This wrapper discovers GraphQL endpoints from the URL inventory
(paths matching common GQL patterns) and creates one execution
pass per endpoint. When no URL inventory exists, it falls back
to base_urls + the default ``/graphql`` path.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.graphql_cop import (
    parse_graphql_cop_json_string,
)
from infrastructure.tools.wrappers.base.graphql_cop import (
    BaseGraphqlCopTool,
)

logger = logging.getLogger(__name__)

_DEFAULT_GQL_PATHS: frozenset[str] = frozenset(
    {
        "/graphql",
        "/gql",
        "/api/graphql",
        "/v1/graphql",
        "/v2/graphql",
        "/query",
    }
)


class GraphqlCopLocalTool(BaseGraphqlCopTool):
    """Concrete local wrapper for graphql-cop."""

    def __init__(self, config=None) -> None:
        self._script_path: str = config.path if config is not None else "graphql-cop.py"
        self._last_target_url: str | None = None

    @property
    def command(self) -> str:
        return "python"

    def check_available(self) -> bool:
        return Path(self._script_path).exists() or (
            shutil.which("graphql-cop") is not None
        )

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs: object) -> list[str]:
        raw = kwargs or {}
        target_url: str | None = str(raw["target_url"]) if "target_url" in raw else None
        headers: dict[str, str] | None = (
            raw.get("headers") or None  # type: ignore[assignment]
        )

        if not target_url:
            raise ValueError("target_url is required for graphql-cop")

        self._last_target_url = target_url

        cmd: list[str] = [
            "python",
            self._script_path,
            "-t",
            target_url,
            "-o",
            "json",
        ]

        if headers:
            cmd.extend(["-H", json.dumps(headers)])

        return cmd

    def parse_output(self, output: str, _files: dict[str, Path]) -> dict[str, Any]:
        try:
            result = parse_graphql_cop_json_string(output)
            result["target_url"] = self._last_target_url or ""
            return result
        finally:
            self._last_target_url = None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
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
        output_dir = paths.tool_output_dir("graphql-cop")
        output_dir.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

        jit_rebuild_artifacts(
            context.base_path,
            context.project_name,
            repo,
            url_finding_repo=url_repo,
        )

        target_urls = self._discover_gql_endpoints(repo, context.service, url_repo)

        if not target_urls:
            logger.warning(
                "graphql-cop: no GraphQL endpoints found for "
                "%s; skipping. Configure graphql_paths on the "
                "service or run URL discovery first.",
                repo.name,
            )
            return []

        passes: list[ExecutionPass] = []
        for url in sorted(target_urls):
            ep_kwargs: dict[str, Any] = {
                "target_url": url,
            }
            if repo.graphql_cop_headers:
                ep_kwargs["headers"] = dict(repo.graphql_cop_headers)

            passes.append(
                ExecutionPass(
                    label_suffix=f"{repo.name} ({url})",
                    kwargs=ep_kwargs,
                )
            )

        return passes

    def _discover_gql_endpoints(self, repo, service, url_repo) -> set[str]:
        from domain.url_inventory.entry import UrlFinding

        target_urls: set[str] = set()

        if repo.id is not None:
            rows: list[UrlFinding] = url_repo.list_for_repo(repo.id)
            gql_paths = set(service.graphql_paths) if service.graphql_paths else None

            for row in rows:
                if gql_paths is not None:
                    if row.path not in gql_paths:
                        continue
                else:
                    if not self._matches_gql_path(row.path):
                        continue

                target_urls.add(self._build_url(row))

        if target_urls:
            return target_urls

        if not service.base_urls:
            return set()

        gql_path_list = service.graphql_paths or ["/graphql"]
        for base in service.base_urls:
            for gql_path in gql_path_list:
                target_urls.add(base.rstrip("/") + gql_path)

        return target_urls

    @staticmethod
    def _matches_gql_path(path: str) -> bool:
        if path in _DEFAULT_GQL_PATHS:
            return True
        return any(
            path.startswith(p + "/") or path.startswith(p + "?")
            for p in _DEFAULT_GQL_PATHS
        )

    @staticmethod
    def _build_url(row) -> str:
        if (row.protocol == "http" and row.port == 80) or (
            row.protocol == "https" and row.port == 443
        ):
            return f"{row.protocol}://{row.host}{row.path}"
        return f"{row.protocol}://{row.host}:{row.port}{row.path}"
