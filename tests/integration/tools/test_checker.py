"""Tests for core/startup/checker.py — no external binaries required."""

import pytest

from application.startup.checker import DependencyChecker

pytestmark = pytest.mark.integration

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
