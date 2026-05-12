"""Tests for startup checker without external binaries."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

from application.startup.checker import DependencyChecker
from domain.tools.interface import ToolInterface

pytestmark = pytest.mark.integration

_LOCAL_WRAPPER_DIR = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "tools"
    / "wrappers"
    / "local"
)


def _expected_tool_names() -> set[str]:
    names: set[str] = set()
    for py in _LOCAL_WRAPPER_DIR.glob("*.py"):
        if py.name.startswith("_"):
            continue
        stem = py.stem
        module_name = f"infrastructure.tools.wrappers.local.{stem}"
        module = importlib.import_module(module_name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, ToolInterface)
                and not inspect.isabstract(cls)
                and cls.__module__ == module_name
            ):
                names.add(cls().name)
    return names


def test_check_system_tools_discovers_all_tools() -> None:
    """check_system_tools() must find every local wrapper.

    This test catches path regressions (e.g. wrappers moving to a new
    layer directory) that would silently empty the Installed System Tools
    display.
    """
    expected = _expected_tool_names()
    checker = DependencyChecker()
    tool_checks = checker.check_system_tools()
    found = {c.name for c in tool_checks}
    assert found == expected, (
        f"Missing: {expected - found}, Unexpected: {found - expected}"
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
