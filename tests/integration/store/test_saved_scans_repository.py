"""Integration tests for SavedScansRepository."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.saved_scans import SavedScanNameConflict  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.saved_scans import (  # noqa: E402
    SavedScansRepository,
)
from infrastructure.store.repositories.tool_arg_profiles import (  # noqa: E402
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


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


def _seed_repo(factory: ConnectionFactory, name: str) -> int:
    with factory.connect() as conn:
        cur = conn.execute("INSERT INTO repositories (name) VALUES (?)", (name,))
        return int(cur.lastrowid)  # type: ignore[arg-type]


def _soft_delete_repo(factory: ConnectionFactory, repo_id: int, when: str) -> None:
    with factory.connect() as conn:
        conn.execute(
            "UPDATE repositories SET deleted_at = ? WHERE id = ?",
            (when, repo_id),
        )


class TestSavedScansRepository:
    def test_insert_round_trip(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_a = _seed_repo(factory, "auth-service")
        repo_b = _seed_repo(factory, "payments")
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a, repo_b],
            tool_names=["gitleaks", "trufflehog"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )
        assert isinstance(rid, int)
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert hydrated.saved_scan.id == rid
        assert hydrated.saved_scan.name == "weekly"
        assert hydrated.saved_scan.skip_enrichment is False
        assert [r.id for r in hydrated.repos] == [repo_a, repo_b]
        assert [r.name for r in hydrated.repos] == ["auth-service", "payments"]
        assert all(r.deleted_at is None for r in hydrated.repos)
        assert [t.tool_name for t in hydrated.tools] == ["gitleaks", "trufflehog"]
        assert [p.id for p in hydrated.arg_profiles] == [profile_id]
        assert hydrated.arg_profiles[0].tool_name == "gitleaks"
        assert hydrated.arg_profiles[0].name == "verbose"

    def test_insert_returns_lastrowid_as_integer(
        self, repo: SavedScansRepository
    ) -> None:
        rid = repo.insert(
            name="x",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_insert_with_empty_join_lists_round_trips(
        self, repo: SavedScansRepository
    ) -> None:
        rid = repo.insert(
            name="empty",
            skip_enrichment=True,
            repo_ids=[],
            tool_names=[],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert hydrated.saved_scan.skip_enrichment is True
        assert hydrated.repos == []
        assert hydrated.tools == []
        assert hydrated.arg_profiles == []

    def test_get_hydrated_returns_none_for_missing(
        self, repo: SavedScansRepository
    ) -> None:
        assert repo.get_hydrated(9999) is None

    def test_get_hydrated_surfaces_soft_deleted_repo(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
    ) -> None:
        active = _seed_repo(factory, "active")
        deleted = _seed_repo(factory, "deleted")
        _soft_delete_repo(factory, deleted, "2026-04-01T12:00:00Z")
        rid = repo.insert(
            name="mixed",
            skip_enrichment=False,
            repo_ids=[active, deleted],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        deleted_marker = {r.id: r.deleted_at for r in hydrated.repos}
        assert deleted_marker[active] is None
        assert deleted_marker[deleted] == "2026-04-01T12:00:00Z"

    def test_insert_with_unknown_repo_id_raises_integrity_error(
        self, repo: SavedScansRepository
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            repo.insert(
                name="bad-repo",
                skip_enrichment=False,
                repo_ids=[9999],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

    def test_insert_with_unknown_arg_profile_id_raises_integrity_error(
        self,
        repo: SavedScansRepository,
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            repo.insert(
                name="bad-profile",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[9999],
            )

    def test_list_for_project_returns_id_arrays_per_row(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_a = _seed_repo(factory, "a")
        repo_b = _seed_repo(factory, "b")
        profile_a = profiles_repo.insert(tool_name="gitleaks", name="p1", args=[])
        profile_b = profiles_repo.insert(tool_name="semgrep", name="p2", args=[])
        rid_1 = repo.insert(
            name="one",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_a],
        )
        rid_2 = repo.insert(
            name="two",
            skip_enrichment=True,
            repo_ids=[repo_a, repo_b],
            tool_names=["gitleaks", "semgrep"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_a, profile_b],
        )
        items, total = repo.list_for_project()
        assert total == 2
        by_id = {item.saved_scan.id: item for item in items}
        assert by_id[rid_1].repo_ids == [repo_a]
        assert by_id[rid_1].tool_names == ["gitleaks"]
        assert by_id[rid_1].arg_profile_ids == [profile_a]
        assert by_id[rid_2].repo_ids == [repo_a, repo_b]
        assert by_id[rid_2].tool_names == ["gitleaks", "semgrep"]
        assert by_id[rid_2].arg_profile_ids == [profile_a, profile_b]

    def test_list_for_project_orders_by_id_ascending(
        self, repo: SavedScansRepository
    ) -> None:
        ids = [
            repo.insert(
                name=name,
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )
            for name in ("zeta", "alpha", "mu")
        ]
        items, _ = repo.list_for_project()
        assert [item.saved_scan.id for item in items] == ids

    def test_list_for_project_respects_offset_and_limit(
        self, repo: SavedScansRepository
    ) -> None:
        ids = [
            repo.insert(
                name=f"s{i}",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )
            for i in range(5)
        ]
        items, total = repo.list_for_project(offset=1, limit=2)
        assert total == 5
        assert [item.saved_scan.id for item in items] == ids[1:3]

    def test_list_for_project_empty_returns_empty(
        self, repo: SavedScansRepository
    ) -> None:
        items, total = repo.list_for_project()
        assert total == 0
        assert items == []

    def test_list_arg_profile_ids_orders_ascending(
        self,
        repo: SavedScansRepository,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        a = profiles_repo.insert(tool_name="gitleaks", name="a", args=[])
        b = profiles_repo.insert(tool_name="gitleaks", name="b", args=[])
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=[],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[b, a],
        )
        assert repo.list_arg_profile_ids(rid) == sorted([a, b])

    def test_list_arg_profile_ids_empty_for_no_profiles(
        self, repo: SavedScansRepository
    ) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        assert repo.list_arg_profile_ids(rid) == []

    def test_replace_rewrites_all_three_join_tables(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_a = _seed_repo(factory, "a")
        repo_b = _seed_repo(factory, "b")
        profile_a = profiles_repo.insert(tool_name="gitleaks", name="p1", args=[])
        profile_b = profiles_repo.insert(tool_name="gitleaks", name="p2", args=[])
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_a],
        )
        repo.replace(
            rid,
            name="weekly",
            skip_enrichment=True,
            repo_ids=[repo_b],
            tool_names=["semgrep", "trufflehog"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_b],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert hydrated.saved_scan.skip_enrichment is True
        assert [r.id for r in hydrated.repos] == [repo_b]
        assert [t.tool_name for t in hydrated.tools] == ["semgrep", "trufflehog"]
        assert [p.id for p in hydrated.arg_profiles] == [profile_b]

    def test_replace_bumps_updated_at(
        self,
        repo: SavedScansRepository,
    ) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        before = repo.get_hydrated(rid)
        assert before is not None
        repo.replace(
            rid,
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        after = repo.get_hydrated(rid)
        assert after is not None
        assert after.saved_scan.updated_at >= before.saved_scan.updated_at
        assert after.saved_scan.created_at == before.saved_scan.created_at

    def test_replace_to_empty_lists_removes_join_rows(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_a = _seed_repo(factory, "a")
        profile_a = profiles_repo.insert(tool_name="gitleaks", name="p", args=[])
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_a],
        )
        repo.replace(
            rid,
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=[],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert hydrated.repos == []
        assert hydrated.tools == []
        assert hydrated.arg_profiles == []

    def test_replace_rolls_back_on_failure_and_keeps_old_rows(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
    ) -> None:
        repo_a = _seed_repo(factory, "a")
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.replace(
                rid,
                name="weekly",
                skip_enrichment=False,
                repo_ids=[9999],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert [r.id for r in hydrated.repos] == [repo_a]
        assert [t.tool_name for t in hydrated.tools] == ["gitleaks"]

    def test_unique_name_raises_conflict_on_insert(
        self, repo: SavedScansRepository
    ) -> None:
        repo.insert(
            name="dup",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        with pytest.raises(SavedScanNameConflict) as excinfo:
            repo.insert(
                name="dup",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["semgrep"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )
        assert excinfo.value.name == "dup"

    def test_unique_name_raises_conflict_on_replace(
        self, repo: SavedScansRepository
    ) -> None:
        first = repo.insert(
            name="a",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        repo.insert(
            name="b",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        with pytest.raises(SavedScanNameConflict) as excinfo:
            repo.replace(
                first,
                name="b",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )
        assert excinfo.value.name == "b"

    def test_delete_cascades_to_join_tables(
        self,
        repo: SavedScansRepository,
        factory: ConnectionFactory,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        repo_a = _seed_repo(factory, "a")
        profile_a = profiles_repo.insert(tool_name="gitleaks", name="p", args=[])
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_a],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_a],
        )
        repo.delete(rid)
        assert repo.get_hydrated(rid) is None
        with factory.connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM saved_scan_repos WHERE saved_scan_id = ?",
                    (rid,),
                ).fetchone()[0]
                == 0
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM saved_scan_tools WHERE saved_scan_id = ?",
                    (rid,),
                ).fetchone()[0]
                == 0
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM saved_scan_arg_profiles"
                    " WHERE saved_scan_id = ?",
                    (rid,),
                ).fetchone()[0]
                == 0
            )

    def test_delete_silent_when_id_missing(self, repo: SavedScansRepository) -> None:
        repo.delete(9999)

    def test_delete_does_not_remove_referenced_arg_profile(
        self,
        repo: SavedScansRepository,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        profile_a = profiles_repo.insert(tool_name="gitleaks", name="p", args=[])
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=[],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_a],
        )
        repo.delete(rid)
        assert profiles_repo.get(profile_a) is not None


class TestFindReferencingArgProfile:
    def test_returns_empty_when_no_saved_scan_references_profile(
        self,
        repo: SavedScansRepository,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        result = repo.find_referencing_arg_profile(profile_id)
        assert result == []

    def test_returns_single_reference_when_one_saved_scan_uses_profile(
        self,
        repo: SavedScansRepository,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        scan_id = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )
        result = repo.find_referencing_arg_profile(profile_id)
        assert len(result) == 1
        assert result[0].id == scan_id
        assert result[0].name == "weekly"

    def test_returns_multiple_references_ordered_by_saved_scan_id(
        self,
        repo: SavedScansRepository,
        profiles_repo: ToolArgProfilesRepository,
    ) -> None:
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        scan_id_1 = repo.insert(
            name="daily",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )
        scan_id_2 = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )
        result = repo.find_referencing_arg_profile(profile_id)
        assert len(result) == 2
        assert result[0].id == scan_id_1
        assert result[0].name == "daily"
        assert result[1].id == scan_id_2
        assert result[1].name == "weekly"
        assert [r.id for r in result] == sorted([scan_id_1, scan_id_2])


class TestSkipToolNamesAndSegments:
    def test_round_trip_through_insert_and_get_hydrated(
        self, repo: SavedScansRepository
    ) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["xsstrike", "nuclei"],
            segments=["sast", "secrets"],
            arg_profile_ids=[],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert set(hydrated.skip_tool_names) == {"xsstrike", "nuclei"}
        assert set(hydrated.segments) == {"sast", "secrets"}

    def test_round_trip_through_replace(self, repo: SavedScansRepository) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["xsstrike"],
            segments=["sast"],
            arg_profile_ids=[],
        )
        repo.replace(
            rid,
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["nuclei", "zap"],
            segments=["sca", "secrets"],
            arg_profile_ids=[],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert set(hydrated.skip_tool_names) == {"nuclei", "zap"}
        assert set(hydrated.segments) == {"sca", "secrets"}

    def test_replace_to_empty_clears_skip_tools_and_segments(
        self, repo: SavedScansRepository
    ) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["xsstrike"],
            segments=["sast"],
            arg_profile_ids=[],
        )
        repo.replace(
            rid,
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        hydrated = repo.get_hydrated(rid)
        assert hydrated is not None
        assert hydrated.skip_tool_names == []
        assert hydrated.segments == []

    def test_list_for_project_includes_skip_tools_and_segments(
        self, repo: SavedScansRepository
    ) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["xsstrike"],
            segments=["sast", "sca"],
            arg_profile_ids=[],
        )
        items, _ = repo.list_for_project()
        item = next(i for i in items if i.saved_scan.id == rid)
        assert item.skip_tool_names == ["xsstrike"]
        assert set(item.segments) == {"sast", "sca"}

    def test_invalid_segment_raises_integrity_error(
        self, repo: SavedScansRepository
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            repo.insert(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=["badvalue"],
                arg_profile_ids=[],
            )

    def test_delete_cascades_to_skip_tools_and_segments(
        self, repo: SavedScansRepository, factory: ConnectionFactory
    ) -> None:
        rid = repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["xsstrike"],
            segments=["sast"],
            arg_profile_ids=[],
        )
        repo.delete(rid)
        with factory.connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM saved_scan_skip_tools"
                    " WHERE saved_scan_id = ?",
                    (rid,),
                ).fetchone()[0]
                == 0
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM saved_scan_segments WHERE saved_scan_id = ?",
                    (rid,),
                ).fetchone()[0]
                == 0
            )
