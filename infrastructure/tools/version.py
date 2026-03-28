import shutil
import subprocess


def get_tool_version(command: str) -> str | None:
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
        return output.splitlines()[0] if output else None
    except Exception:
        return None
