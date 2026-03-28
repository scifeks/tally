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
    assert attrs == {"executor", "registry", "factory"}


def test_domain_base_does_not_import_application() -> None:
    base_path = (
        Path(__file__).parent.parent.parent.parent
        / "domain"
        / "tools"
        / "scan_types"
        / "base.py"
    )
    source = base_path.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("application"), (
                    f"domain/tools/scan_types/base.py imports from application: "
                    f"{node.module}"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("application"), (
                        f"domain/tools/scan_types/base.py imports from application: "
                        f"{alias.name}"
                    )
