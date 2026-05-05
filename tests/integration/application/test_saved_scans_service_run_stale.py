"""Integration tests for SavedScansService.run_saved_scan staleness validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.saved_scans.errors import StaleSavedScanError
from application.saved_scans.service import (
    SavedScanNotFound,
    SavedScansService,
)
from application.tools.registry import ToolRegistry
from domain.saved_scans.entry import (
    StaleSavedScanArgProfileItem,
    StaleSavedScanRepoItem,
    StaleSavedScanToolItem,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.saved_scans import (
    SavedScansRepository,
)
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


class _StubTool:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> SavedScansRepository:
    return SavedScansRepository(factory)


@pytest.fixture()
def profiles_repo(factory: ConnectionFactory) -> ToolArgProfilesRepository:
    return ToolArgProfilesRepository(factory)


@pytest.fixture()
def tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in ("gitleaks", "trufflehog", "semgrep"):
        registry.register(_StubTool(name))
    return registry


@pytest.fixture()
def service(
    repo: SavedScansRepository,
    profiles_repo: ToolArgProfilesRepository,
    tool_registry: ToolRegistry,
) -> SavedScansService:
    return SavedScansService(repo, profiles_repo, tool_registry)


def _seed_repo_row(factory: ConnectionFactory, name: str) -> int:
    with factory.connect() as conn:
        cur = conn.execute("INSERT INTO repositories (name) VALUES (?)", (name,))
        return int(cur.lastrowid)  # type: ignore[arg-type]


def _soft_delete_repo(factory: ConnectionFactory, repo_id: int, when: str) -> None:
    with factory.connect() as conn:
        conn.execute(
            "UPDATE repositories SET deleted_at = ? WHERE id = ?",
            (when, repo_id),
        )


def _drop_profile_with_fk_off(factory: ConnectionFactory, profile_id: int) -> None:
    with factory.connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM tool_arg_profiles WHERE id = ?", (profile_id,))
        conn.execute("PRAGMA foreign_keys = ON")


class TestRunSavedScanStaleness:
    def test_clean_run_returns_hydrated(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_id = _seed_repo_row(factory, "auth-service")
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])

        hydrated = service.create(
            name="weekly",
            skip_enrichment=True,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )

        result = service.run_saved_scan(hydrated.saved_scan.id)

        assert result.saved_scan.id == hydrated.saved_scan.id
        assert [r.id for r in result.repos] == [repo_id]
        assert [t.tool_name for t in result.tools] == ["gitleaks"]
        assert [p.id for p in result.arg_profiles] == [profile_id]

    def test_missing_saved_scan_raises_not_found(
        self,
        service: SavedScansService,
    ) -> None:
        with pytest.raises(SavedScanNotFound) as excinfo:
            service.run_saved_scan(999)
        assert excinfo.value.saved_scan_id == 999

    def test_soft_deleted_repo_marks_stale(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
    ) -> None:
        repo_id = _seed_repo_row(factory, "auth-service")
        hydrated = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        _soft_delete_repo(factory, repo_id, "2026-05-03T00:00:00Z")

        with pytest.raises(StaleSavedScanError) as excinfo:
            service.run_saved_scan(hydrated.saved_scan.id)

        stale_items = excinfo.value.stale_items
        assert len(stale_items) == 1
        assert isinstance(stale_items[0], StaleSavedScanRepoItem)
        assert stale_items[0].id == repo_id
        assert stale_items[0].name == "auth-service"
        assert stale_items[0].kind == "repo"

    def test_unregistered_tool_marks_stale(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
        tool_registry: ToolRegistry,
    ) -> None:
        repo_id = _seed_repo_row(factory, "auth-service")
        hydrated = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        # Unregister the tool.
        tool_registry.clear()

        with pytest.raises(StaleSavedScanError) as excinfo:
            service.run_saved_scan(hydrated.saved_scan.id)

        stale_items = excinfo.value.stale_items
        assert len(stale_items) == 1
        assert isinstance(stale_items[0], StaleSavedScanToolItem)
        assert stale_items[0].name == "gitleaks"
        assert stale_items[0].kind == "tool"

    def test_orphan_arg_profile_marks_stale(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_id = _seed_repo_row(factory, "auth-service")
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        hydrated = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )

        _drop_profile_with_fk_off(factory, profile_id)

        with pytest.raises(StaleSavedScanError) as excinfo:
            service.run_saved_scan(hydrated.saved_scan.id)

        stale_items = excinfo.value.stale_items
        assert len(stale_items) == 1
        assert isinstance(stale_items[0], StaleSavedScanArgProfileItem)
        assert stale_items[0].id == profile_id
        assert stale_items[0].kind == "argProfile"

    def test_multiple_stale_categories_aggregated(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
        tool_registry: ToolRegistry,
    ) -> None:
        repo_id = _seed_repo_row(factory, "auth-service")
        profile_id = profiles_repo.insert(tool_name="semgrep", name="security", args=[])
        hydrated = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["semgrep"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )

        # Soft-delete the repo.
        _soft_delete_repo(factory, repo_id, "2026-05-03T00:00:00Z")

        # Unregister semgrep.
        tool_registry.clear()

        # Drop the profile.
        _drop_profile_with_fk_off(factory, profile_id)

        with pytest.raises(StaleSavedScanError) as excinfo:
            service.run_saved_scan(hydrated.saved_scan.id)

        stale_items = excinfo.value.stale_items
        assert len(stale_items) == 3
        assert [s.kind for s in stale_items] == ["repo", "tool", "argProfile"]

    def test_clean_run_with_empty_repo_list_no_op(
        self,
        service: SavedScansService,
    ) -> None:
        hydrated = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        result = service.run_saved_scan(hydrated.saved_scan.id)

        assert result.saved_scan.id == hydrated.saved_scan.id
        assert result.repos == []
        assert [t.tool_name for t in result.tools] == ["gitleaks"]
        assert result.arg_profiles == []
