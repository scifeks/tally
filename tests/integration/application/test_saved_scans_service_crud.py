"""Integration tests for SavedScansService."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.ports.saved_scans import SavedScanNameConflict
from application.saved_scans.service import (
    SavedScanNotFound,
    SavedScansService,
    SavedScanValidationError,
)
from application.tools.registry import ToolRegistry
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


class TestSavedScansServiceIntegration:
    def test_create_round_trip_returns_hydrated(
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

        assert hydrated.saved_scan.name == "weekly"
        assert hydrated.saved_scan.skip_enrichment is True
        assert [r.id for r in hydrated.repos] == [repo_id]
        assert [t.tool_name for t in hydrated.tools] == ["gitleaks"]
        assert [p.id for p in hydrated.arg_profiles] == [profile_id]

    def test_create_unique_name_conflict_is_typed(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
    ) -> None:
        _seed_repo_row(factory, "auth-service")
        service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        with pytest.raises(SavedScanNameConflict):
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["trufflehog"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

    def test_create_validation_error_persists_nothing(
        self,
        service: SavedScansService,
    ) -> None:
        with pytest.raises(SavedScanValidationError):
            service.create(
                name="",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        items, total = service.list()
        assert total == 0
        assert items == []

    def test_create_at_least_one_of_tool_names_or_profile_ids_required(
        self,
        service: SavedScansService,
    ) -> None:
        with pytest.raises(SavedScanValidationError):
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

    def test_create_unknown_tool_name_raises(
        self,
        service: SavedScansService,
    ) -> None:
        with pytest.raises(SavedScanValidationError):
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["not-a-tool"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

    def test_create_unknown_arg_profile_id_raises(
        self,
        service: SavedScansService,
    ) -> None:
        with pytest.raises(SavedScanValidationError):
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[999],
            )

    def test_list_returns_total_and_rows(
        self,
        service: SavedScansService,
    ) -> None:
        for label in ("alpha", "beta"):
            service.create(
                name=label,
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        items, total = service.list()
        assert total == 2
        assert {item.saved_scan.name for item in items} == {"alpha", "beta"}

    def test_get_returns_hydrated_when_present(
        self,
        service: SavedScansService,
    ) -> None:
        created = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        result = service.get(created.saved_scan.id)
        assert result is not None
        assert result.saved_scan.name == "weekly"

    def test_get_returns_none_when_absent(
        self,
        service: SavedScansService,
    ) -> None:
        assert service.get(999) is None

    def test_replace_swaps_joins_and_returns_hydrated(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_a = _seed_repo_row(factory, "auth-service")
        repo_b = _seed_repo_row(factory, "payments")
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        original = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        result = service.replace(
            original.saved_scan.id,
            name="weekly",
            skip_enrichment=True,
            repo_ids=[repo_b],
            tool_names=["trufflehog"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )

        assert result.saved_scan.skip_enrichment is True
        assert [r.id for r in result.repos] == [repo_b]
        assert [t.tool_name for t in result.tools] == ["trufflehog"]
        assert [p.id for p in result.arg_profiles] == [profile_id]

    def test_replace_missing_id_raises_not_found(
        self,
        service: SavedScansService,
    ) -> None:
        with pytest.raises(SavedScanNotFound) as excinfo:
            service.replace(
                999,
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )
        assert excinfo.value.saved_scan_id == 999

    def test_replace_unique_name_conflict(
        self,
        service: SavedScansService,
    ) -> None:
        first = service.create(
            name="alpha",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        service.create(
            name="beta",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        with pytest.raises(SavedScanNameConflict):
            service.replace(
                first.saved_scan.id,
                name="beta",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

    def test_delete_removes_row_and_cascades_joins(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
    ) -> None:
        repo_a = _seed_repo_row(factory, "auth-service")
        created = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        service.delete(created.saved_scan.id)

        assert service.get(created.saved_scan.id) is None
        with factory.connect() as conn:
            tools = conn.execute(
                "SELECT 1 FROM saved_scan_tools WHERE saved_scan_id = ?",
                (created.saved_scan.id,),
            ).fetchall()
            repos = conn.execute(
                "SELECT 1 FROM saved_scan_repos WHERE saved_scan_id = ?",
                (created.saved_scan.id,),
            ).fetchall()
        assert tools == []
        assert repos == []

    def test_delete_silent_when_id_missing(
        self,
        service: SavedScansService,
    ) -> None:
        # Should not raise.
        service.delete(999)

    def test_full_round_trip(
        self,
        service: SavedScansService,
        factory: ConnectionFactory,
    ) -> None:
        repo_a = _seed_repo_row(factory, "auth-service")
        created = service.create(
            name="alpha",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        listed_items, listed_total = service.list()
        assert listed_total == 1
        assert listed_items[0].saved_scan.id == created.saved_scan.id

        fetched = service.get(created.saved_scan.id)
        assert fetched is not None and fetched.saved_scan.name == "alpha"

        replaced = service.replace(
            created.saved_scan.id,
            name="alpha-2",
            skip_enrichment=True,
            repo_ids=[],
            tool_names=["semgrep"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        assert replaced.saved_scan.name == "alpha-2"

        service.delete(created.saved_scan.id)
        assert service.get(created.saved_scan.id) is None
