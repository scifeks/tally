import re
import shutil
import subprocess

from domain.runtime.models import RuntimeDependencyRequirement, RuntimeDependencyStatus

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SEMVER_RE = re.compile(r"\d+\.\d+[\d.]*")

_REQUIREMENT = RuntimeDependencyRequirement(
    name="claude",
    binary="claude",
    install_hint="See https://code.claude.com/docs/en/quickstart",
    required_for=("triage",),
)


class ClaudeCodeProbe:
    @property
    def requirement(self) -> RuntimeDependencyRequirement:
        return _REQUIREMENT

    def probe(self) -> RuntimeDependencyStatus:
        binary = shutil.which("claude")
        if binary is None:
            return RuntimeDependencyStatus(
                name=_REQUIREMENT.name,
                installed=False,
                binary_path=None,
                version=None,
                install_hint=_REQUIREMENT.install_hint,
                required_for=_REQUIREMENT.required_for,
                error="claude not on PATH",
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
                    name=_REQUIREMENT.name,
                    installed=False,
                    binary_path=binary,
                    version=None,
                    install_hint=_REQUIREMENT.install_hint,
                    required_for=_REQUIREMENT.required_for,
                    error=f"claude --version failed: {reason}",
                )
            clean = _ANSI_RE.sub("", output)
            match = _SEMVER_RE.search(clean)
            return RuntimeDependencyStatus(
                name=_REQUIREMENT.name,
                installed=True,
                binary_path=binary,
                version=match.group(0) if match else None,
                install_hint=_REQUIREMENT.install_hint,
                required_for=_REQUIREMENT.required_for,
                error=None,
            )
        except subprocess.TimeoutExpired:
            return RuntimeDependencyStatus(
                name=_REQUIREMENT.name,
                installed=False,
                binary_path=binary,
                version=None,
                install_hint=_REQUIREMENT.install_hint,
                required_for=_REQUIREMENT.required_for,
                error="claude --version failed: timed out",
            )
        except Exception as exc:
            return RuntimeDependencyStatus(
                name=_REQUIREMENT.name,
                installed=False,
                binary_path=binary,
                version=None,
                install_hint=_REQUIREMENT.install_hint,
                required_for=_REQUIREMENT.required_for,
                error=f"claude --version failed: {exc}",
            )
