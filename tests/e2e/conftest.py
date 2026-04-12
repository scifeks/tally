"""E2e-test configuration.

Autouse fixture:

_cleanup_chromadb_systems — stops all ChromaDB Systems after each test to
prevent file-handle accumulation (EMFILE) across the full suite.

Note: _restore_tool_registry is defined in tests/conftest.py and covers all
test scopes including e2e.

Harness fixtures:

tally_harness — isolated TallyHarness backed by tmp_path; calls setup(),
    spawn(), and teardown() automatically.

tally_harness_live — TallyHarness pointed at the real repo root; useful for
    interactive debugging sessions where you want to inspect real project data.
    Does NOT call setup() or teardown() automatically.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from chromadb.api.shared_system_client import SharedSystemClient

from tests.e2e.harness import TallyHarness


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


@pytest.fixture()
def tally_harness(tmp_path: Path) -> Generator[TallyHarness]:
    """Isolated TallyHarness for e2e tests.

    Copies global.json from the real repo into tmp_path, sets
    location_attestation_confirmed=true, spawns the REPL, and tears it
    down after the test.  The project namespace is entirely separate from
    the developer's real data.
    """
    harness = TallyHarness(base_path=tmp_path)
    harness.setup()
    commands_cfg = tmp_path / "config" / "commands.json"
    if not commands_cfg.exists():
        commands_cfg.write_text(json.dumps({}))
    harness.spawn()
    yield harness
    harness.teardown()


@pytest.fixture()
def tally_harness_live() -> Generator[TallyHarness]:
    """Live TallyHarness pointed at the real repo root.

    Spawns against your actual config and projects — useful for debugging
    a specific implementation.  You are responsible for any data created
    during the test.
    """
    harness = TallyHarness()
    harness.spawn()
    yield harness
    harness.teardown()
