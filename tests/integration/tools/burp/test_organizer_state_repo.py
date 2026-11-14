"""Integration tests for OrganizerStateRepository."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from infrastructure.store.repositories.organizer_state import (  # noqa: E402
    OrganizerStateRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "test.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> OrganizerStateRepository:
    return OrganizerStateRepository(factory)


class TestOrganizerStateRepository:
    def test_empty_state_returns_empty_set(
        self, repo: OrganizerStateRepository
    ) -> None:
        assert repo.get_ingested_ids(1) == set()

    def test_mark_and_retrieve(self, repo: OrganizerStateRepository) -> None:
        repo.mark_ingested(1, 42)
        repo.mark_ingested(1, 99)
        assert repo.get_ingested_ids(1) == {42, 99}

    def test_idempotent_mark(self, repo: OrganizerStateRepository) -> None:
        repo.mark_ingested(1, 42)
        repo.mark_ingested(1, 42)
        assert repo.get_ingested_ids(1) == {42}

    def test_project_isolation(self, repo: OrganizerStateRepository) -> None:
        repo.mark_ingested(1, 10)
        repo.mark_ingested(2, 20)
        assert repo.get_ingested_ids(1) == {10}
        assert repo.get_ingested_ids(2) == {20}
