"""Shared docker exec command builder for docker tool wrappers."""


def build_docker_exec(
    container_name: str,
    tool_path: str,
    tool_args: list[str],
    workdir: str | None = None,
) -> list[str]:
    cmd = ["docker", "exec"]
    if workdir:
        cmd.extend(["-w", workdir])
    cmd.extend([container_name, tool_path])
    cmd.extend(tool_args)
    return cmd
