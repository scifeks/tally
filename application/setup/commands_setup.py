"""First-run interactive setup: generates config/commands.json."""

import importlib
import inspect
import json
import shutil
from pathlib import Path


def _get_wrapper_meta(tool_name: str, location: str = "local") -> dict:
    """Return {candidate_commands, tool_type} from wrapper class attributes."""
    from domain.tools.interface import ToolInterface

    stem = tool_name.replace("-", "_")
    try:
        module = importlib.import_module(
            f"infrastructure.tools.wrappers.{location}.{stem}"
        )
    except ImportError:
        return {"candidate_commands": [tool_name], "tool_type": "repo"}
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, ToolInterface)
            and not inspect.isabstract(obj)
            and obj.__module__ == module.__name__
        ):
            return {
                "candidate_commands": getattr(obj, "_candidate_commands", [tool_name]),
                "tool_type": getattr(obj, "_command_entry_type", "repo"),
            }
    return {"candidate_commands": [tool_name], "tool_type": "repo"}


# Characters that are unsafe in command tokens
_METACHAR_CHARS = frozenset(";&|<>`$")


def _has_metachar(s: str) -> bool:
    return any(ch in s for ch in _METACHAR_CHARS)


def _warn_metachar(label: str, value: str) -> None:
    if _has_metachar(value):
        print(
            f"  Warning: {label} contains shell metacharacters; verify this is correct."
        )


def find_local_binary(tool_name: str) -> str | None:
    """Return the first binary found on PATH for tool_name, or None."""
    meta = _get_wrapper_meta(tool_name, location="local")
    for cmd in meta["candidate_commands"]:
        found = shutil.which(cmd)
        if found:
            return found
    return None


def _discover_wrapper_tools(location: str) -> list[str]:
    wrappers_dir = (
        Path(__file__).parent.parent.parent
        / "infrastructure"
        / "tools"
        / "wrappers"
        / location
    )
    return sorted(
        p.stem.replace("_", "-")
        for p in wrappers_dir.glob("*.py")
        if p.stem != "__init__"
    )


def resolve_local_binary(tool_name: str, configured_path: str | None) -> str | None:
    """Resolve the local binary path for tool_name."""
    if (
        configured_path
        and configured_path != "skip"
        and not _has_metachar(configured_path)
        and shutil.which(configured_path)
    ):
        return configured_path
    return find_local_binary(tool_name)


def load_commands_json(base_path: str) -> dict[str, dict]:
    path = Path(base_path) / "config" / "commands.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def reconcile_commands_with_system(existing: dict[str, dict]) -> dict[str, dict]:
    """Reconcile existing commands with system state."""
    reconciled: dict[str, dict] = {}

    for name, entry in existing.items():
        if entry.get("location") == "docker":
            reconciled[name] = dict(entry)

    for tool_name in _discover_wrapper_tools("local"):
        if tool_name in reconciled:
            continue
        configured_path = (existing.get(tool_name) or {}).get("path")
        resolved = resolve_local_binary(tool_name, configured_path)
        if resolved is None:
            continue
        meta = _get_wrapper_meta(tool_name, "local")
        reconciled[tool_name] = {
            "type": meta["tool_type"],
            "location": "local",
            "path": resolved,
        }

    return dict(sorted(reconciled.items()))


def sync_commands_config(base_path: str) -> None:
    existing = load_commands_json(base_path)
    reconciled = reconcile_commands_with_system(existing)
    commands_path = Path(base_path) / "config" / "commands.json"
    if commands_path.exists() and json.loads(commands_path.read_text()) == reconciled:
        return
    commands_path.parent.mkdir(parents=True, exist_ok=True)
    commands_path.write_text(json.dumps(reconciled, indent=2))


def interview_local(tool_name: str, defaults: dict | None = None) -> dict | None:
    """Collect local binary path for tool_name. Returns a raw dict or None to skip.

    In edit mode (defaults is not None and has 'path'), shows current value and
    Enter keeps it. In add mode, performs binary detection and manual entry.
    """
    if defaults is not None and defaults.get("path"):
        current_path = defaults["path"]
        print(f"  Current path: {current_path}")
        path = input(f"  Enter new path [{current_path}]: ").strip()
        if not path:
            path = current_path
    else:
        found = find_local_binary(tool_name)
        if found:
            print(f"  Local binary found: {found}")
            raw = input("  Use this path? [Y/n]: ").strip().lower()
            if raw in ("", "y", "yes"):
                path = found
            else:
                path = input(f"  Enter path to {tool_name} binary: ").strip()
                if not path:
                    print("  Skipping.")
                    return None
        else:
            print(f"  {tool_name} not found on PATH.")
            path = input("  Enter path manually (or press Enter to skip): ").strip()
            if not path:
                return None

    path = path.strip()
    _warn_metachar("binary path", path)
    tool_type = _get_wrapper_meta(tool_name, location="local")["tool_type"]
    return {
        "type": tool_type,
        "location": "local",
        "path": path,
    }


def interview_docker(tool_name: str, defaults: dict | None = None) -> dict | None:
    """Collect Docker container config for tool_name.

    Returns a raw dict or None to skip.

    In add mode (defaults is None), asks the gate question "Run in Docker?".
    In edit mode (defaults is not None), skips the gate and shows current values;
    Enter keeps each current value.
    """
    if defaults is None:
        raw = input(f"  Run {tool_name} in a Docker container? [y/N]: ").strip().lower()
        if raw not in ("y", "yes"):
            return None
        current_name = ""
        current_tool_path = ""
    else:
        current_name = (defaults.get("container") or {}).get("name", "")
        current_tool_path = (defaults.get("container") or {}).get("tool_path", "")

    if defaults is not None:
        name_input = input(f"  Container name [{current_name}]: ").strip()
        container = name_input if name_input else current_name
    else:
        container = input("  Container name: ").strip()

    if not container:
        print("  Container name is required. Skipping.")
        return None
    _warn_metachar("container name", container)

    if defaults is not None:
        tp_input = input(
            f"  Path to {tool_name} binary inside the container [{current_tool_path}]: "
        ).strip()
        tool_path = tp_input if tp_input else current_tool_path
    else:
        tool_path = input(
            f"  Path to {tool_name} binary inside the container: "
        ).strip()

    if not tool_path:
        print("  Binary path is required. Skipping.")
        return None
    _warn_metachar("binary path", tool_path)

    tool_type = _get_wrapper_meta(tool_name, location="docker")["tool_type"]
    return {
        "type": tool_type,
        "location": "docker",
        "container": {"name": container, "tool_path": tool_path},
    }


def interview_tool(
    tool_name: str, has_local: bool, has_docker: bool, defaults: dict | None = None
) -> dict | None:
    """Full interview for a single tool. Returns raw CommandEntry dict or None.

    In add mode (defaults is None), prompts to configure from scratch.
    In edit mode (defaults is not None), shows current location and allows
    keeping, updating, or switching the configuration.
    """
    print(f"\n[{tool_name}]")

    if defaults is None:
        if has_local and has_docker:
            found = find_local_binary(tool_name)
            if found:
                print(f"  Local binary found: {found}")
            choice = (
                input("  Run locally or via Docker? [local/docker/skip]: ")
                .strip()
                .lower()
            )
            if choice == "docker":
                return interview_docker(tool_name)
            elif choice == "local":
                return interview_local(tool_name)
            else:
                print("  Skipping.")
                return None
        elif has_local:
            return interview_local(tool_name)
        elif has_docker:
            return interview_docker(tool_name)
        return None

    # Edit mode
    current_location = defaults.get("location", "local")
    print(f"  current: {current_location}")

    if has_local and has_docker:
        choice = (
            input("  Run locally or via Docker? [local/docker/keep]: ").strip().lower()
        )
        if choice == "local":
            if current_location == "local":
                return interview_local(tool_name, defaults=defaults)
            else:
                return interview_local(tool_name, defaults={})
        elif choice == "docker":
            if current_location == "docker":
                return interview_docker(tool_name, defaults=defaults)
            else:
                return interview_docker(tool_name, defaults={})
        else:
            # keep (Enter or unrecognised)
            if current_location == "docker":
                return interview_docker(tool_name, defaults=defaults)
            else:
                return interview_local(tool_name, defaults=defaults)
    elif has_local:
        return interview_local(tool_name, defaults=defaults)
    elif has_docker:
        return interview_docker(tool_name, defaults=defaults)
    return None


def run_commands_setup(base_path: str) -> None:
    """Run the interactive first-run setup and write config/commands.json.

    Scans wrappers/local/ and wrappers/docker/ to discover available tool
    names, interviews the user for each, and writes the result.

    Args:
        base_path: Application root directory (where config/ lives).
    """
    wrappers_dir = (
        Path(__file__).parent.parent.parent / "infrastructure" / "tools" / "wrappers"
    )
    local_dir = wrappers_dir / "local"
    docker_dir = wrappers_dir / "docker"

    local_tools = {
        f.stem.replace("_", "-")
        for f in local_dir.glob("*.py")
        if not f.name.startswith("_")
    }
    docker_tools = {
        f.stem.replace("_", "-")
        for f in docker_dir.glob("*.py")
        if not f.name.startswith("_")
    }

    all_tools = sorted(local_tools | docker_tools)

    print("\nTally - First-Run Tool Setup")
    print("=" * 40)
    print("Configure which security tools to use and how to run them.")
    print("(Delete config/commands.json to re-run this setup at any time.)\n")

    commands: dict[str, dict] = {}

    for tool_name in all_tools:
        entry = interview_tool(
            tool_name,
            has_local=tool_name in local_tools,
            has_docker=tool_name in docker_tools,
        )
        if entry is not None:
            commands[tool_name] = entry

    # Write directly; ConfigManager requires global.json which may not exist yet
    config_dir = Path(base_path) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "commands.json", "w") as f:
        json.dump(commands, f, indent=2)

    print("\n" + "=" * 40)
    print(f"Setup complete. {len(commands)} tool(s) configured:")
    for name, entry in commands.items():
        loc = entry.get("location", "?")
        detail = entry.get("path", "") or entry.get("container", {}).get("name", "")
        print(f"  + {name:<18} ({loc}) {detail}")
    if not commands:
        print("  (none: all tools skipped)")
    print("\nconfig/commands.json written.")
    print(
        "If anything was misconfigured, delete config/commands.json and re-run tally.\n"
    )
