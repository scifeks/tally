"""Validation-test configuration.

Autouse fixture that stops all ChromaDB systems after every test to prevent
file-handle accumulation (EMFILE) when running the full suite.
"""

from __future__ import annotations

import pytest
from chromadb.api.shared_system_client import SharedSystemClient


@pytest.fixture(autouse=True)
def _cleanup_chromadb_systems():
    """Stop and evict every ChromaDB System created during this test."""
    yield
    for system in list(SharedSystemClient._identifier_to_system.values()):
        try:
            system.stop()
        except Exception:
            pass
    SharedSystemClient._identifier_to_system.clear()
    SharedSystemClient._identifier_to_refcount.clear()
