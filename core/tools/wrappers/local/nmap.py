import shutil
from pathlib import Path
from typing import Any

from ...base import ToolWrapper
from ...parsers.nmap_parser import parse_nmap_xml, parse_nmap_xml_string


class NmapWrapper(ToolWrapper):
    def __init__(self, config=None) -> None:
        pass

    @property
    def name(self) -> str:
        return "nmap"

    @property
    def command(self) -> str:
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
    def supported_languages(self) -> list[str] | None:
        return None

    def check_available(self) -> bool:
        return shutil.which("nmap") is not None

    def build_command(self, **kwargs) -> list[str]:
        """Build the nmap argv list.

        Keyword Args:
            profile (str):      Name of a profile in nmap_hosts.json.
            hosts (List[str]):  Explicit list of hosts/subnets to scan.
            args (str):         Additional nmap arguments (override profile args).
            project_name (str): Required when using *profile*.
            base_path (str|Path): App base path for ConfigManager (default ".").
        """
        profile: str | None = kwargs.get("profile")
        hosts: list[str] | None = kwargs.get("hosts")
        args: str = kwargs.get("args", "")
        project_name: str | None = kwargs.get("project_name")
        base_path = kwargs.get("base_path", ".")

        if profile is not None:
            if not project_name:
                raise ValueError("project_name is required when using a profile")

            from core.config import ConfigManager
            from core.setup.nmap_setup import check_exclusion_conflicts

            config = ConfigManager(base_path=str(base_path))
            nmap_config = config.load_nmap_hosts(project_name)
            if not nmap_config or not nmap_config.profiles:
                raise ValueError(
                    f"No nmap_hosts.json found for project: {project_name!r}"
                )
            if profile not in nmap_config.profiles:
                available = list(nmap_config.profiles.keys())
                raise ValueError(
                    f"Profile {profile!r} not found. Available profiles: {available}"
                )

            nmap_profile = nmap_config.profiles[profile]
            hosts = nmap_profile.hosts
            if not args:
                args = nmap_profile.nmap_args

            conflicts = check_exclusion_conflicts(hosts, nmap_config.excluded_networks)
            if conflicts:
                raise ValueError(
                    f"Profile '{profile}' targets are in the exclusion list: "
                    f"{conflicts}. Fix with: tool edit nmap"
                )

        elif hosts is not None:
            if not isinstance(hosts, list):
                raise ValueError("hosts must be a list of strings")
        else:
            raise ValueError("Either 'profile' or 'hosts' must be provided")

        # -oX - writes XML to stdout so the executor can capture and save it
        return ["nmap"] + (args.split() if args else []) + ["-oX", "-"] + list(hosts)

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse nmap XML output into structured data.

        Prefers the saved stdout file; falls back to parsing the output string.
        """
        xml_path = files.get("stdout")
        if xml_path is not None and xml_path.exists():
            return parse_nmap_xml(xml_path)
        return parse_nmap_xml_string(output)
