"""E2e-test configuration.

Autouse fixture:

_cleanup_chromadb_systems: stops all ChromaDB Systems after each test to
prevent file-handle accumulation (EMFILE) across the full suite.

Note: _restore_tool_registry is defined in tests/conftest.py and covers all
test scopes including e2e.

Harness fixtures:

tally_harness: isolated TallyHarness backed by tmp_path; calls setup(),
    spawn(), and teardown() automatically.

tally_harness_live: TallyHarness pointed at the real repo root; useful for
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


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Cap xdist auto worker count to half of available CPUs.

    Long-running scan tests (semgrep, gitleaks, domain scans) spawn
    CPU-heavy subprocesses. Running 16 pytest workers simultaneously
    starves those subprocesses and causes pexpect timeouts. Halving the
    worker count leaves enough CPU headroom for scans to complete.
    """
    import os

    return max(2, (os.cpu_count() or 4) // 2)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Assign xdist worker groups to prevent unsafe concurrency.

    Three tiers:
    - tally_harness tests: fully isolated (tmp_path REPL per test),
      run in parallel across all workers with no group assigned.
    - tally_harness_live tests: share the real repo root (findings.db,
      ChromaDB), pinned to group "live" so they serialize on one worker.
    - e2e-marked tests: hit a shared Ollama server; concurrent embedding
      requests pile up and time out. Pinned to group "ollama" so they
      serialize on one worker (independent of the live group).
    """
    for item in items:
        marks = {m.name for m in item.iter_markers()}
        if "tally_harness_live" in getattr(item, "fixturenames", []):
            item.add_marker(pytest.mark.xdist_group("live"))
        elif "e2e" in marks:
            item.add_marker(pytest.mark.xdist_group("ollama"))


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

    Spawns against your actual config and projects for debugging a
    specific implementation. You are responsible for any data created
    during the test.
    """
    harness = TallyHarness()
    harness.spawn()
    yield harness
    harness.teardown()
