"""Docker wrapper for OWASP ZAP dynamic web application security testing.

ZAP writes its report to a path inside the container filesystem which is not
accessible from the host without a shared volume mount.  The wrapper therefore
targets a temp path inside the container and falls back to parsing stdout
(ZAP's progress output) for any structured data.  This is a known limitation:
structured JSON report data is unavailable without a shared volume.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.zap import (
    parse_zap_json,
    parse_zap_json_string,
)
from infrastructure.tools.wrappers.base.zap import BaseZapTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec

logger = logging.getLogger(__name__)


class ZAPDockerTool(BaseZapTool):
    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path
        self._container_report_path: str | None = None

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs) -> list[str]:
        """Build docker exec argv for ZAP."""
        base_url: str | None = kwargs.get("base_url")
        if not base_url:
            raise ValueError("base_url is required for ZAP")

        openapi_file: str | None = kwargs.get("openapi_file")

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        report_path = f"/tmp/tally_zap_{ts}.json"
        self._container_report_path = report_path

        tool_args: list[str] = ["-cmd"]

        if openapi_file:
            tool_args.extend(
                [
                    "-openapifile",
                    openapi_file,
                    "-openapitargeturl",
                    base_url,
                ]
            )

        tool_args.extend(
            [
                "-quickurl",
                base_url,
                "-quickprogress",
                "-quickout",
                report_path,
            ]
        )
        return build_docker_exec(self._container_name, self._tool_path, tool_args)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse ZAP output from stdout."""
        stdout_path = files.get("stdout")
        if stdout_path is not None and stdout_path.exists():
            return parse_zap_json(stdout_path)
        return parse_zap_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for ZAP.

        Falls back to quick-scan mode when no URL inventory exists.
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
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        url_repo = UrlFindingRepository(factory)

        kwargs: dict[str, Any] = {
            "base_url": repo.base_urls[0],
        }

        _seeds_path, oas3_path = jit_rebuild_artifacts(
            context.base_path,
            context.project_name,
            repo,
            url_finding_repo=url_repo,
        )
        if oas3_path:
            kwargs["openapi_file"] = oas3_path
        else:
            logger.info(
                "ZAP: no URL inventory for %s; using quick-scan mode.",
                repo.name,
            )

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
