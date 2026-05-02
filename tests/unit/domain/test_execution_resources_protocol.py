"""Tests for IExecutionResources domain Protocol."""

from __future__ import annotations

import ast
from pathlib import Path


def test_iexecution_resources_is_in_domain() -> None:
    from domain.tools.scan_types.resources import IExecutionResources

    assert isinstance(IExecutionResources, type)


def test_iexecution_resources_declares_required_attributes() -> None:
    from domain.tools.scan_types.resources import IExecutionResources

    attrs: set[str] = getattr(IExecutionResources, "__protocol_attrs__")
    assert attrs == {
        "executor",
        "registry",
        "factory",
        "event_bus",
        "display",
        "event_sink",
    }


def test_domain_scan_types_package_does_not_import_application() -> None:
    package_dir = (
        Path(__file__).parent.parent.parent.parent / "domain" / "tools" / "scan_types"
    )
    for py_file in package_dir.glob("*.py"):
        source = py_file.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("application"), (
                    f"{py_file.name} imports from application: {node.module}"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("application"), (
                        f"{py_file.name} imports from application: {alias.name}"
                    )
