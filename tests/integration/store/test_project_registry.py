"""Unit tests for ProjectRegistryRepository."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from infrastructure.store.project_registry import ProjectRegistryRepository

pytestmark = pytest.mark.integration


def _seed_project_dir(base: Path, name: str) -> Path:
    project_dir = base / "projects" / name
    (project_dir / "config").mkdir(parents=True)
    (project_dir / "config" / "project.json").write_text(
        json.dumps({"project_name": name, "repositories": []})
    )
    return project_dir


@pytest.fixture
def repo(tmp_path: Path) -> ProjectRegistryRepository:
    repository = ProjectRegistryRepository(tmp_path / "tally.db")
    repository.init_schema()
    return repository


class TestInitSchema:
    def test_creates_projects_table(self, tmp_path: Path) -> None:
        repo = ProjectRegistryRepository(tmp_path / "tally.db")
        repo.init_schema()
        with sqlite3.connect(str(repo.db_path)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
            ).fetchone()
        assert row is not None

    def test_idempotent(self, tmp_path: Path) -> None:
        repo = ProjectRegistryRepository(tmp_path / "tally.db")
        repo.init_schema()
        repo.init_schema()
        repo.init_schema()
        with sqlite3.connect(str(repo.db_path)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='projects'"
            ).fetchone()[0]
        assert count == 1

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "tally.db"
        repo = ProjectRegistryRepository(nested)
        repo.init_schema()
        assert nested.parent.exists()


class TestInsertAndLookup:
    def test_insert_returns_id(self, repo: ProjectRegistryRepository) -> None:
        new_id = repo.insert("foo", "/abs/path/foo")
        assert new_id > 0

    def test_get_by_id_roundtrip(self, repo: ProjectRegistryRepository) -> None:
        new_id = repo.insert("foo", "/abs/path/foo")
        row = repo.get_by_id(new_id)
        assert row is not None
        assert row.id == new_id
        assert row.name == "foo"
        assert row.path == "/abs/path/foo"
        assert row.archived_at is None
        assert row.created_at is not None

    def test_get_by_name_roundtrip(self, repo: ProjectRegistryRepository) -> None:
        new_id = repo.insert("bar", "/abs/path/bar")
        row = repo.get_by_name("bar")
        assert row is not None
        assert row.id == new_id

    def test_get_unknown_returns_none(self, repo: ProjectRegistryRepository) -> None:
        assert repo.get_by_id(9999) is None
        assert repo.get_by_name("nonexistent") is None

    def test_unique_name_constraint(self, repo: ProjectRegistryRepository) -> None:
        repo.insert("foo", "/p1")
        with pytest.raises(sqlite3.IntegrityError):
            repo.insert("foo", "/p2")


class TestArchiveLifecycle:
    def test_archive_sets_archived_at(self, repo: ProjectRegistryRepository) -> None:
        repo.insert("foo", "/p/foo")
        repo.archive("foo")
        row = repo.get_by_name("foo")
        assert row is not None
        assert row.archived_at is not None

    def test_list_active_excludes_archived(
        self, repo: ProjectRegistryRepository
    ) -> None:
        repo.insert("active1", "/p/a1")
        repo.insert("archived1", "/p/ar1")
        repo.archive("archived1")
        names = [r.name for r in repo.list_active()]
        assert "active1" in names
        assert "archived1" not in names

    def test_list_all_includes_archived(self, repo: ProjectRegistryRepository) -> None:
        repo.insert("active1", "/p/a1")
        repo.insert("archived1", "/p/ar1")
        repo.archive("archived1")
        names = [r.name for r in repo.list_all()]
        assert "active1" in names
        assert "archived1" in names

    def test_unarchive_clears_and_updates_path(
        self, repo: ProjectRegistryRepository
    ) -> None:
        repo.insert("foo", "/old/path")
        repo.archive("foo")
        repo.unarchive("foo", "/new/path")
        row = repo.get_by_name("foo")
        assert row is not None
        assert row.archived_at is None
        assert row.path == "/new/path"


class TestRename:
    def test_rename_updates_name_and_path(
        self, repo: ProjectRegistryRepository
    ) -> None:
        new_id = repo.insert("old", "/p/old")
        repo.rename("old", "new", "/p/new")
        assert repo.get_by_name("old") is None
        row = repo.get_by_name("new")
        assert row is not None
        assert row.id == new_id
        assert row.path == "/p/new"


class TestSyncFromFilesystem:
    def test_inserts_new_projects(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        _seed_project_dir(tmp_path, "alpha")
        _seed_project_dir(tmp_path, "beta")
        repo.sync_from_filesystem(str(tmp_path))
        names = sorted(r.name for r in repo.list_active())
        assert names == ["alpha", "beta"]

    def test_paths_are_absolute(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        _seed_project_dir(tmp_path, "alpha")
        repo.sync_from_filesystem(str(tmp_path))
        row = repo.get_by_name("alpha")
        assert row is not None
        assert Path(row.path).is_absolute()
        assert Path(row.path) == (tmp_path / "projects" / "alpha").resolve()

    def test_skips_dirs_without_project_json(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        (tmp_path / "projects" / "incomplete").mkdir(parents=True)
        repo.sync_from_filesystem(str(tmp_path))
        assert repo.get_by_name("incomplete") is None

    def test_skips_dotted_dirs(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        (tmp_path / "projects").mkdir(parents=True)
        (tmp_path / "projects" / ".hidden").mkdir()
        repo.sync_from_filesystem(str(tmp_path))
        assert repo.list_active() == []

    def test_archives_disappeared_dirs(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        proj_dir = _seed_project_dir(tmp_path, "ghost")
        repo.sync_from_filesystem(str(tmp_path))
        seeded = repo.get_by_name("ghost")
        assert seeded is not None
        assert seeded.archived_at is None

        import shutil

        shutil.rmtree(proj_dir)
        repo.sync_from_filesystem(str(tmp_path))
        row = repo.get_by_name("ghost")
        assert row is not None
        assert row.archived_at is not None

    def test_unarchives_reappeared_dirs(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        repo.insert("phoenix", str((tmp_path / "projects" / "phoenix").resolve()))
        repo.archive("phoenix")
        _seed_project_dir(tmp_path, "phoenix")
        repo.sync_from_filesystem(str(tmp_path))
        row = repo.get_by_name("phoenix")
        assert row is not None
        assert row.archived_at is None

    def test_idempotent(self, repo: ProjectRegistryRepository, tmp_path: Path) -> None:
        _seed_project_dir(tmp_path, "alpha")
        _seed_project_dir(tmp_path, "beta")
        repo.sync_from_filesystem(str(tmp_path))
        repo.sync_from_filesystem(str(tmp_path))
        repo.sync_from_filesystem(str(tmp_path))
        names = sorted(r.name for r in repo.list_active())
        assert names == ["alpha", "beta"]

    def test_no_projects_dir_is_safe(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        repo.sync_from_filesystem(str(tmp_path))
        assert repo.list_active() == []

    def test_updates_path_when_dir_moved_within_base(
        self, repo: ProjectRegistryRepository, tmp_path: Path
    ) -> None:
        repo.insert("alpha", "/stale/path/alpha")
        _seed_project_dir(tmp_path, "alpha")
        repo.sync_from_filesystem(str(tmp_path))
        row = repo.get_by_name("alpha")
        assert row is not None
        assert Path(row.path) == (tmp_path / "projects" / "alpha").resolve()
