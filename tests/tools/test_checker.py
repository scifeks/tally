"""Tests for core/startup/checker.py — no external binaries required."""

from core.startup.checker import DependencyChecker

_EXPECTED_TOOLS = {
    "composer-audit",
    "gitleaks",
    "nmap",
    "npm-audit",
    "osv-scanner",
    "pip-audit",
    "semgrep",
    "zap",
}


def test_check_system_tools_discovers_all_tools() -> None:
    """check_system_tools() must find every local wrapper.

    This test catches path regressions (e.g. wrappers moving to a new
    layer directory) that would silently empty the Installed System Tools
    display.
    """
    checker = DependencyChecker()
    tool_checks = checker.check_system_tools()
    found = {c.name for c in tool_checks}
    assert found == _EXPECTED_TOOLS, (
        f"Missing: {_EXPECTED_TOOLS - found}, Unexpected: {found - _EXPECTED_TOOLS}"
    )


def test_check_system_tools_returns_dep_checks() -> None:
    """Each entry must be a DepCheck with the expected fields populated."""
    from core.startup.checker import DepCheck

    checker = DependencyChecker()
    tool_checks = checker.check_system_tools()

    for check in tool_checks:
        assert isinstance(check, DepCheck)
        assert check.type == "system_tool"
        assert check.name in _EXPECTED_TOOLS
        assert isinstance(check.installed, bool)
