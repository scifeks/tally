"""Docker wrapper for OWASP ZAP dynamic web application security testing.

ZAP writes its report to a path inside the container filesystem which is not
accessible from the host without a shared volume mount.  The wrapper therefore
targets a temp path inside the container and falls back to parsing stdout
(ZAP's progress output) for any structured data.  This is a known limitation:
structured JSON report data is unavailable without a shared volume.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...base import DockerToolWrapper, ToolResult
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.zap_parser import parse_zap_json, parse_zap_json_string


class DockerZAPWrapper(ToolInterface, DockerToolWrapper):
    def __init__(self, config) -> None:
        super().__init__(config)
        self._container_report_path: str | None = None

    @property
    def name(self) -> str:
        return "zap"

    @property
    def category(self) -> str:
        return "api"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "OWASP ZAP dynamic web application security scanner"

    @property
    def scan_segment(self) -> str:
        return "api"

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def requires_base_urls(self) -> bool:
        return True

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def build_command(self, **kwargs) -> list[str]:
        """Build docker exec argv for ZAP quick-scan.

        Keyword Args:
            base_url (str): API base URL to scan. Required.
            endpoints (Dict): Endpoint map (informational only in quick-scan mode).
            output_file (str): Ignored for docker — report is written inside container.
        """
        base_url: str | None = kwargs.get("base_url")
        if not base_url:
            raise ValueError("base_url is required for ZAP")

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        report_path = f"/tmp/tally_zap_{ts}.json"
        self._container_report_path = report_path

        tool_args = [
            "-cmd",
            "-quickurl",
            base_url,
            "-quickprogress",
            "-quickout",
            report_path,
        ]
        return self._build_docker_exec(tool_args)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse ZAP output from stdout.

        The report file is written inside the container and cannot be read from
        the host without a shared volume.  stdout (progress messages) is used
        as the data source; structured JSON is unavailable in this mode.
        """
        stdout_path = files.get("stdout")
        if stdout_path is not None and stdout_path.exists():
            return parse_zap_json(stdout_path)
        return parse_zap_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"base_url": context.repo.base_urls[0]},
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        result = summary.get("total_alerts", len(parsed_data.get("alerts", [])))
        # TODO: revisit when normalized schema is introduced
        return result
