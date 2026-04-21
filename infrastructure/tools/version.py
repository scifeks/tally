import re
import shutil
import subprocess

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SEMVER_RE = re.compile(r"\d+\.\d+[\d.]*")


def get_tool_version(command: str) -> str | None:
    """Run ``<command> --version`` and return the first semver found.

    Strips ANSI escape codes before searching.  Returns ``None`` when the
    binary is not on PATH, the command fails, or no semver pattern is found
    in the output.  Callers that need a different invocation (e.g. DalFox's
    ``version`` subcommand) should override ``get_version()`` directly.
    """
    binary = shutil.which(command)
    if binary is None:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr).strip()
        if not output:
            return None
        clean = _ANSI_RE.sub("", output)
        match = _SEMVER_RE.search(clean)
        return match.group(0) if match else None
    except Exception:
        return None
