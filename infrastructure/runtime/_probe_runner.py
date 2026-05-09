import re
import shutil
import subprocess

from domain.runtime.models import (
    RuntimeDependencyRequirement,
    RuntimeDependencyStatus,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SEMVER_RE = re.compile(r"\d+\.\d+[\d.]*")


def run_version_probe(
    req: RuntimeDependencyRequirement,
) -> RuntimeDependencyStatus:
    binary = shutil.which(req.binary)
    if binary is None:
        return RuntimeDependencyStatus(
            name=req.name,
            installed=False,
            binary_path=None,
            version=None,
            install_hint=req.install_hint,
            required_for=req.required_for,
            error=f"{req.binary} not on PATH",
        )
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr).strip()
        if not output or result.returncode != 0:
            reason = (
                f"exit {result.returncode}"
                if result.returncode != 0
                else "empty output"
            )
            return RuntimeDependencyStatus(
                name=req.name,
                installed=False,
                binary_path=binary,
                version=None,
                install_hint=req.install_hint,
                required_for=req.required_for,
                error=(f"{req.binary} --version failed: {reason}"),
            )
        clean = _ANSI_RE.sub("", output)
        match = _SEMVER_RE.search(clean)
        return RuntimeDependencyStatus(
            name=req.name,
            installed=True,
            binary_path=binary,
            version=match.group(0) if match else None,
            install_hint=req.install_hint,
            required_for=req.required_for,
            error=None,
        )
    except subprocess.TimeoutExpired:
        return RuntimeDependencyStatus(
            name=req.name,
            installed=False,
            binary_path=binary,
            version=None,
            install_hint=req.install_hint,
            required_for=req.required_for,
            error=f"{req.binary} --version failed: timed out",
        )
    except Exception as exc:
        return RuntimeDependencyStatus(
            name=req.name,
            installed=False,
            binary_path=binary,
            version=None,
            install_hint=req.install_hint,
            required_for=req.required_for,
            error=f"{req.binary} --version failed: {exc}",
        )
