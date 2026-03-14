"""Shared base class for nmap local and docker wrappers."""

from pathlib import Path
from typing import Any

from ...base import ToolResult
from ...interface import ExecutionContext, ExecutionPass, ToolInterface
from ...parsers.nmap_parser import parse_nmap_xml, parse_nmap_xml_string


class BaseNmapTool(ToolInterface):
    _DEFAULT_NMAP_ARGS = "-sV -sC -O"

    @property
    def name(self) -> str:
        return "nmap"

    @property
    def category(self) -> str:
        return "network"

    @property
    def scope(self) -> str:
        return "project"

    @property
    def description(self) -> str:
        return "Network mapper for host discovery and port scanning"

    @property
    def scan_segment(self) -> str:
        return "network"

    @property
    def findings_exit_ok(self) -> bool:
        return False

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse nmap XML output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        xml_path = files.get("stdout")
        if xml_path is not None and xml_path.exists():
            return parse_nmap_xml(xml_path)
        return parse_nmap_xml_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        nmap_config = context.config_manager.load_nmap_hosts(context.project_name)
        passes = []
        for profile_name in nmap_config.profiles if nmap_config else {}:
            passes.append(
                ExecutionPass(
                    label_suffix=profile_name,
                    kwargs={
                        "profile": profile_name,
                        "project_name": context.project_name,
                        "base_path": context.base_path,
                    },
                )
            )
        return passes

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        if len(pass_results) == 1:
            return pass_results[0]

        # Combine unique hosts; later profiles override earlier for same IP
        hosts_by_ip: dict[str, Any] = {}
        for result in pass_results:
            pd = result.parsed_data or {}
            if "error" in pd:
                continue
            for host in pd.get("hosts", []):
                ip = host.get("ip_address") or f"_noip_{id(host)}"
                hosts_by_ip[ip] = host

        first_pd = pass_results[0].parsed_data or {}
        combined_data: dict[str, Any] = {
            "scan_info": first_pd.get("scan_info", {}),
            "hosts": list(hosts_by_ip.values()),
        }

        combined_files: dict[str, Path] = {}
        for result in pass_results:
            combined_files.update(result.output_files)

        return ToolResult(
            tool_name="nmap",
            success=any(r.success for r in pass_results),
            output="\n".join(r.output or "" for r in pass_results).strip(),
            parsed_data=combined_data,
            output_files=combined_files,
            timestamp=pass_results[0].timestamp,
            duration_seconds=sum(r.duration_seconds for r in pass_results),
        )

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        # TODO: revisit when normalized schema is introduced
        return len(parsed_data.get("hosts", []))
