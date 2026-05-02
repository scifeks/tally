"""Tests for startup checker without external binaries."""

from __future__ import annotations

import importlib

import pytest

from application.startup.checker import DependencyChecker

pytestmark = pytest.mark.integration

_EXPECTED_TOOLS = {
    "composer-audit",
    "dalfox",
    "gitleaks",
    "katana",
    "noir",
    "npm-audit",
    "osv-scanner",
    "pip-audit",
    "semgrep",
    "xsstrike",
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


def test_check_python_packages_uses_distribution_metadata_not_module_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = DependencyChecker()

    def _unexpected_import(name: str):
        raise AssertionError(f"unexpected module import: {name}")

    monkeypatch.setattr(importlib, "import_module", _unexpected_import)

    checks = checker.check_python_packages()

    assert checks
    assert any(c.name == "onnxruntime" for c in checks)
