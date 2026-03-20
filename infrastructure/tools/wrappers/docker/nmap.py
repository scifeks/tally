"""Docker wrapper for nmap network scanning."""

from infrastructure.tools.wrappers.base.nmap import BaseNmapTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class NmapDockerTool(BaseNmapTool):
    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs) -> list[str]:
        """Build docker exec argv for nmap.

        Keyword Args:
            profile (str):        Profile name from nmap_hosts.json.
            hosts (List[str]):    Explicit host/subnet list.
            args (str):           Additional nmap arguments.
            project_name (str):   Required when using a profile.
            base_path (str|Path): App base path (default ".").
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
                args = nmap_profile.nmap_args or self._DEFAULT_NMAP_ARGS

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

        # -oX - writes XML to stdout; executor captures it
        tool_args = (args.split() if args else []) + ["-oX", "-"] + list(hosts)
        return build_docker_exec(self._container_name, self._tool_path, tool_args)
