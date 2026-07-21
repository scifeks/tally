"""list_active succeeds when a repo's path no longer exists on disk."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas.repo_service import RepoService  # noqa: E402
from core.config.schemas.repository import Repository  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    RepositoryRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def repo_repo(tmp_path: Path) -> RepositoryRepository:
    db_path = tmp_path / "findings.db"
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    return RepositoryRepository(factory)


def test_list_active_tolerates_missing_path(
    repo_repo: RepositoryRepository, tmp_path: Path
) -> None:
    """Verify list_active works even when a repo's path has been deleted."""
    vanished = tmp_path / "repo_that_vanishes"
    vanished.mkdir()

    repo = Repository(
        name="vanishing-repo",
        path=str(vanished),
        services=[
            RepoService(
                name="svc",
                type=["api"],
                languages=["python"],
            )
        ],
    )
    repo_repo.insert(repo)

    vanished.rmdir()
    assert not vanished.exists()

    repos = repo_repo.list_active()
    assert len(repos) == 1
    assert repos[0].name == "vanishing-repo"
    assert repos[0].path == str(vanished)
