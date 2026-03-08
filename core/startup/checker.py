"""Dependency checker for tally startup validation."""

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

_INSTALL_HINTS = {
    "nmap": "sudo apt install nmap  OR  brew install nmap",
    "semgrep": "pip install semgrep",
    "osv-scanner": "go install github.com/google/osv-scanner/cmd/osv-scanner@latest",
    "pip-audit": "pip install pip-audit",
    "npm-audit": "Included with Node.js: https://nodejs.org",
    "composer-audit": "Included with Composer: https://getcomposer.org",
    "gitleaks": "brew install gitleaks  OR  https://github.com/gitleaks/gitleaks/releases",
    "zap": "https://www.zaproxy.org/download/",
}

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
    type: str  # 'python', 'package', 'system_tool'
    required: bool
    installed: bool
    version: str | None = None
    install_hint: str | None = None


@dataclass
class CheckResult:
    checks: list[DepCheck]
    all_required_present: bool
    missing_required: list[DepCheck]
    missing_optional: list[DepCheck]


class DependencyChecker:
    def __init__(self, tool_registry) -> None:
        self._registry = tool_registry
        self._console = Console()

    def run(self, auto_fix: bool = False) -> CheckResult:
        checks: list[DepCheck] = []

        checks.append(self.check_python_version())
        checks.extend(self.check_python_packages())
        checks.extend(self.check_system_tools())

        missing_required = [c for c in checks if c.required and not c.installed]
        missing_optional = [c for c in checks if not c.required and not c.installed]
        all_required_present = len(missing_required) == 0

        result = CheckResult(
            checks=checks,
            all_required_present=all_required_present,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )

        self.print_summary(result)
        return result

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
                    required=True,
                    installed=installed,
                    version=version,
                    install_hint=f"pip install {pkg_name}" if not installed else None,
                )
            )

        return results

    def check_system_tools(self) -> list[DepCheck]:
        results: list[DepCheck] = []
        for tool in self._registry.get_all_tools():
            config = self._registry.get_tool_config(tool.name)
            if config is not None and config.location == "docker":
                # Docker tools are always "installed" — the user explicitly
                # configured them
                results.append(
                    DepCheck(
                        name=tool.name,
                        type="docker",
                        required=False,
                        installed=True,
                        version=None,
                        install_hint=f"Container: {config.container.name}",
                    )
                )
            else:
                # Local tool or fallback mode — check binary availability as before
                available = tool.check_available()
                version = tool.get_version() if available else None
                results.append(
                    DepCheck(
                        name=tool.name,
                        type="system_tool",
                        required=False,
                        installed=available,
                        version=version,
                        install_hint=_INSTALL_HINTS.get(tool.name),
                    )
                )
        return results

    def print_summary(self, result: CheckResult) -> None:
        self._console.print("\n[bold]Tally - Dependency Check[/bold]")
        self._console.print("=" * 24)

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("Dependency", style="cyan", min_width=18)
        table.add_column("Type", min_width=12)
        table.add_column("Status", min_width=14)
        table.add_column("Install Hint")

        for check in result.checks:
            if check.installed:
                status = f"[green]v {check.version or 'installed'}[/green]"
            else:
                status = "[yellow]! NOT FOUND[/yellow]"

            hint = check.install_hint or ""
            table.add_row(check.name, check.type, status, hint)

        self._console.print(table)

        if result.missing_optional:
            count = len(result.missing_optional)
            self._console.print(
                f"[yellow]Warning: {count} optional "
                f"tool{'s' if count != 1 else ''} not found. "
                f"Some scan features will be unavailable.[/yellow]"
            )

        if result.missing_required:
            count = len(result.missing_required)
            names = ", ".join(c.name for c in result.missing_required)
            self._console.print(
                f"[red]Error: {count} required dependency missing: {names}[/red]"
            )

        self._console.print(
            "[dim]Run 'tally --check' to see full dependency status at any time.[/dim]"
        )
