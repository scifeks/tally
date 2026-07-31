"""Docker wrapper for graphql-cop GraphQL security auditing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.graphql_cop import (
    parse_graphql_cop_json_string,
)
from infrastructure.tools.wrappers.base.graphql_cop import (
    BaseGraphqlCopTool,
)
from infrastructure.tools.wrappers.docker._docker_exec import (
    build_docker_exec,
)

logger = logging.getLogger(__name__)


class GraphqlCopDockerTool(BaseGraphqlCopTool):
    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path
        self._last_target_url: str | None = None

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs) -> list[str]:
        target_url: str | None = kwargs.get("target_url")
        if not target_url:
            raise ValueError("target_url is required for graphql-cop")

        self._last_target_url = target_url
        headers: dict[str, str] | None = kwargs.get("headers") or None

        tool_args: list[str] = [
            "-t",
            target_url,
            "-o",
            "json",
        ]

        if headers:
            tool_args.extend(["-H", json.dumps(headers)])

        return build_docker_exec(
            self._container_name,
            self._tool_path,
            tool_args,
        )

    def parse_output(self, output: str, _files: dict[str, Path]) -> dict[str, Any]:
        try:
            result = parse_graphql_cop_json_string(output)
            result["target_url"] = self._last_target_url or ""
            return result
        finally:
            self._last_target_url = None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        from infrastructure.tools.wrappers.utils.auth_login import (
            build_tool_headers,
        )

        assert context.repo is not None
        assert context.service is not None

        kwargs: dict[str, Any] = {
            "target_url": context.service.base_urls[0],
        }
        headers = build_tool_headers(
            context.repo.auth, context.repo.graphql_cop_headers
        )
        if headers:
            kwargs["headers"] = headers

        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs=kwargs,
            )
        ]
