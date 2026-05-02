"""Dependency checker for tally startup validation."""

from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.runtime import RuntimeDependencyService

_INSTALL_HINTS = {
    "semgrep": "pip install semgrep",
    "osv-scanner": "go install github.com/google/osv-scanner/cmd/osv-scanner@latest",
    "pip-audit": "pip install pip-audit",
    "npm-audit": "Included with Node.js: https://nodejs.org",
    "composer-audit": "Included with Composer: https://getcomposer.org",
    "gitleaks": "https://github.com/gitleaks/gitleaks?tab=readme-ov-file#installing",
    "zap": "https://www.zaproxy.org/download/",
    "xsstrike": (
        "git clone https://github.com/s0md3v/XSStrike && "
        "pip install fuzzywuzzy python-Levenshtein"
    ),
}

# Minimum compatible versions for system tools (major, minor, patch).
_MIN_VERSIONS: dict[str, tuple[int, ...]] = {
    "gitleaks": (8, 30, 0),
}


def _parse_version(version_str: str) -> tuple[int, ...] | None:
    """Parse 'v8.30.0' or '8.30.0' into (8, 30, 0), or None on failure."""
    cleaned = version_str.lstrip("v").split()[0]
    try:
        return tuple(int(p) for p in cleaned.split("."))
    except ValueError:
        return None


# Map package names in requirements.txt to importable module names
_PACKAGE_IMPORT_MAP = {
    "pydantic": "pydantic",
    "rich": "rich",
    "prompt_toolkit": "prompt_toolkit",
    "chromadb": "chromadb",
    "ollama": "ollama",
    "pytest": "pytest",
    "pytest-timeout": "pytest_timeout",
}


@dataclass
class DepCheck:
    name: str
    type: str  # 'python', 'package', 'system_tool', 'runtime_dep'
    required: bool
    installed: bool
    version: str | None = None
    install_hint: str | None = None
    warning: str | None = None


@dataclass
class CheckResult:
    checks: list[DepCheck]
    all_required_present: bool
    missing_required: list[DepCheck]
    missing_optional: list[DepCheck]


class DependencyChecker:
    def __init__(self, runtime_service: RuntimeDependencyService | None = None) -> None:
        self._runtime_service = runtime_service

    def run(self, auto_fix: bool = False) -> CheckResult:
        checks: list[DepCheck] = []

        checks.append(self.check_python_version())
        checks.extend(self.check_python_packages())
        checks.extend(self.check_system_tools())
        if self._runtime_service is not None:
            for status in self._runtime_service.statuses():
                checks.append(
                    DepCheck(
                        name=status.name,
                        type="runtime_dep",
                        required=True,
                        installed=status.installed,
                        version=status.version,
                        install_hint=status.install_hint,
                    )
                )

        missing_required = [c for c in checks if c.required and not c.installed]
        missing_optional = [c for c in checks if not c.required and not c.installed]
        all_required_present = len(missing_required) == 0

        return CheckResult(
            checks=checks,
            all_required_present=all_required_present,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )

    def check_python_version(self) -> DepCheck:
        major = sys.version_info.major
        minor = sys.version_info.minor
        micro = sys.version_info.micro
        version_str = f"{major}.{minor}.{micro}"
        installed = major > 3 or (major == 3 and minor >= 10)
        return DepCheck(
            name="python",
            type="python",
            required=True,
            installed=installed,
            version=version_str if installed else None,
            install_hint="https://www.python.org/downloads/" if not installed else None,
        )

    def check_python_packages(self) -> list[DepCheck]:
        req_path = Path(__file__).parent.parent.parent / "requirements.txt"
        results: list[DepCheck] = []

        if not req_path.exists():
            return results

        with open(req_path) as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

        for line in lines:
            # Strip version specifiers (>=, ==, etc.)
            pkg_name = (
                line.split(">=")[0].split("==")[0].split("!=")[0].split("~=")[0].strip()
            )
            if not pkg_name:
                continue

            module_name = _PACKAGE_IMPORT_MAP.get(pkg_name, pkg_name.replace("-", "_"))

            try:
                mod = importlib.import_module(module_name)
                version = getattr(mod, "__version__", None)
                installed = True
            except ImportError:
                version = None
                installed = False

            results.append(
                DepCheck(
                    name=pkg_name,
                    type="package",
                    required=False,
                    installed=installed,
                    version=version,
                    install_hint=f"pip install {pkg_name}" if not installed else None,
                )
            )

        return results

    def check_system_tools(self) -> list[DepCheck]:
        from domain.tools.interface import ToolInterface

        results: list[DepCheck] = []
        local_dir = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "tools"
            / "wrappers"
            / "local"
        )

        for py_file in sorted(local_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            module_name = f"infrastructure.tools.wrappers.local.{py_file.stem}"
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue

            for _attr, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, ToolInterface)
                    and not inspect.isabstract(obj)
                    and obj.__module__ == module_name
                ):
                    try:
                        tool = obj(config=None)  # type: ignore[call-arg]
                    except Exception:
                        break
                    available = tool.check_available()  # type: ignore[attr-defined]
                    version = tool.get_version() if available else None  # type: ignore[attr-defined]
                    dep = DepCheck(
                        name=tool.name,
                        type="system_tool",
                        required=False,
                        installed=available,
                        version=version,
                        install_hint=_INSTALL_HINTS.get(tool.name),
                    )
                    if available and version and tool.name in _MIN_VERSIONS:
                        parsed = _parse_version(version)
                        min_ver = _MIN_VERSIONS[tool.name]
                        if parsed is not None and parsed < min_ver:
                            min_str = ".".join(str(p) for p in min_ver)
                            dep.warning = (
                                f"Version {version} is not compatible."
                                f" Requires >= v{min_str}."
                            )
                    results.append(dep)
                    break

        return results
