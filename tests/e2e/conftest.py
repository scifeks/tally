"""E2e-test configuration.

Two autouse fixtures:

1. _restore_tool_registry — saves the tool_registry singleton state before
   each test and restores it after. E2e tests that call discover_tools() clear
   and repopulate the global singleton; without this fixture those mutations
   bleed into subsequent integration tests that depend on the registry.

2. _cleanup_chromadb_systems — stops all ChromaDB Systems after each test to
   prevent file-handle accumulation (EMFILE) across the full suite.
"""

from __future__ import annotations

import pytest
from chromadb.api.shared_system_client import SharedSystemClient

from application.tools.registry import tool_registry


@pytest.fixture(autouse=True)
def _restore_tool_registry():
    saved_tools = dict(tool_registry._tools)
    saved_configs = dict(tool_registry._configs)
    yield
    tool_registry._tools.clear()
    tool_registry._tools.update(saved_tools)
    tool_registry._configs.clear()
    tool_registry._configs.update(saved_configs)


@pytest.fixture(autouse=True)
def _cleanup_chromadb_systems():
    yield
    for system in list(SharedSystemClient._identifier_to_system.values()):
        try:
            system.stop()
        except Exception:
            pass
    SharedSystemClient._identifier_to_system.clear()
    SharedSystemClient._identifier_to_refcount.clear()
