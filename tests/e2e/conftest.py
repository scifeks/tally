"""E2e-test configuration.

Autouse fixture:

_cleanup_chromadb_systems — stops all ChromaDB Systems after each test to
prevent file-handle accumulation (EMFILE) across the full suite.

Note: _restore_tool_registry is defined in tests/conftest.py and covers all
test scopes including e2e.
"""

from __future__ import annotations

import pytest
from chromadb.api.shared_system_client import SharedSystemClient


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
