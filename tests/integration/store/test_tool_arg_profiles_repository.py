"""Integration tests for ToolArgProfilesRepository."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.tool_arg_profiles import (  # noqa: E402
    ToolArgProfileNameConflict,
)
from domain.tool_arg_profiles.entry import (  # noqa: E402
    ToolArgProfileArg,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
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
def repo(factory: ConnectionFactory) -> ToolArgProfilesRepository:
    return ToolArgProfilesRepository(factory)


class TestToolArgProfilesRepository:
    def test_insert_round_trip_preserves_all_three_arg_types(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        args = [
            ToolArgProfileFlagArg(name="--verbose"),
            ToolArgProfileStringArg(name="--config", value="p/owasp"),
            ToolArgProfileFileArg(name="--rules", path="arg_files/1/--rules.yml"),
        ]
        rid = repo.insert(tool_name="gitleaks", name="verbose", args=args)
        row = repo.get(rid)
        assert row is not None
        assert row.id == rid
        assert row.tool_name == "gitleaks"
        assert row.name == "verbose"
        assert row.args == args

    def test_insert_round_trip_preserves_original_filename(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        args: list[ToolArgProfileArg] = [
            ToolArgProfileFileArg(
                name="--rules",
                path="arg_files/1/--rules",
                original_filename="custom.yml",
            ),
        ]
        rid = repo.insert(tool_name="gitleaks", name="fn-test", args=args)
        row = repo.get(rid)
        assert row is not None
        assert isinstance(row.args[0], ToolArgProfileFileArg)
        assert row.args[0].original_filename == "custom.yml"

    def test_insert_round_trip_handles_missing_original_filename(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        args: list[ToolArgProfileArg] = [
            ToolArgProfileFileArg(name="--rules", path="arg_files/1/--rules"),
        ]
        rid = repo.insert(tool_name="gitleaks", name="no-fn", args=args)
        row = repo.get(rid)
        assert row is not None
        assert isinstance(row.args[0], ToolArgProfileFileArg)
        assert row.args[0].original_filename is None

    def test_insert_returns_lastrowid_as_integer(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        rid = repo.insert(tool_name="gitleaks", name="a", args=[])
        assert isinstance(rid, int)
        assert rid > 0

    def test_list_paginated_returns_rows_and_total(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        repo.insert(tool_name="gitleaks", name="a", args=[])
        repo.insert(tool_name="gitleaks", name="b", args=[])
        repo.insert(tool_name="semgrep", name="c", args=[])
        rows, total = repo.list_paginated()
        assert total == 3
        assert {r.name for r in rows} == {"a", "b", "c"}

    def test_list_paginated_filter_by_tool_name(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        repo.insert(tool_name="gitleaks", name="a", args=[])
        repo.insert(tool_name="gitleaks", name="b", args=[])
        repo.insert(tool_name="semgrep", name="c", args=[])
        rows, total = repo.list_paginated(tool_name="gitleaks")
        assert total == 2
        assert {r.name for r in rows} == {"a", "b"}
        assert all(r.tool_name == "gitleaks" for r in rows)

    def test_list_paginated_respects_offset_and_limit(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        ids = [
            repo.insert(tool_name="gitleaks", name=f"p{i}", args=[]) for i in range(5)
        ]
        rows, total = repo.list_paginated(offset=1, limit=2)
        assert total == 5
        assert [r.id for r in rows] == ids[1:3]

    def test_update_replaces_args_and_bumps_updated_at(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        rid = repo.insert(
            tool_name="gitleaks",
            name="verbose",
            args=[ToolArgProfileFlagArg(name="--verbose")],
        )
        before = repo.get(rid)
        assert before is not None
        repo.update(
            rid,
            tool_name="gitleaks",
            name="verbose",
            args=[ToolArgProfileStringArg(name="--config", value="x")],
        )
        after = repo.get(rid)
        assert after is not None
        assert after.args == [ToolArgProfileStringArg(name="--config", value="x")]
        assert after.updated_at >= before.updated_at
        assert after.created_at == before.created_at

    def test_delete_removes_row(self, repo: ToolArgProfilesRepository) -> None:
        rid = repo.insert(tool_name="gitleaks", name="x", args=[])
        repo.delete(rid)
        assert repo.get(rid) is None

    def test_delete_blocked_when_referenced_by_saved_scan(
        self,
        repo: ToolArgProfilesRepository,
        factory: ConnectionFactory,
    ) -> None:
        profile_id = repo.insert(tool_name="gitleaks", name="ref", args=[])
        with factory.connect() as conn:
            scan_cur = conn.execute(
                "INSERT INTO saved_scans (name) VALUES (?)", ("weekly",)
            )
            conn.execute(
                "INSERT INTO saved_scan_arg_profiles"
                " (saved_scan_id, arg_profile_id) VALUES (?, ?)",
                (scan_cur.lastrowid, profile_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            repo.delete(profile_id)

    def test_unique_tool_name_name_raises_conflict_on_insert(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        repo.insert(tool_name="gitleaks", name="dup", args=[])
        with pytest.raises(ToolArgProfileNameConflict) as excinfo:
            repo.insert(tool_name="gitleaks", name="dup", args=[])
        assert excinfo.value.tool_name == "gitleaks"
        assert excinfo.value.name == "dup"

    def test_unique_tool_name_name_raises_conflict_on_update(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        first = repo.insert(tool_name="gitleaks", name="a", args=[])
        repo.insert(tool_name="gitleaks", name="b", args=[])
        with pytest.raises(ToolArgProfileNameConflict) as excinfo:
            repo.update(first, tool_name="gitleaks", name="b", args=[])
        assert excinfo.value.tool_name == "gitleaks"
        assert excinfo.value.name == "b"

    def test_unique_constraint_scoped_per_tool(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        repo.insert(tool_name="gitleaks", name="verbose", args=[])
        # Same name under a different tool is allowed.
        repo.insert(tool_name="semgrep", name="verbose", args=[])
        _, total = repo.list_paginated()
        assert total == 2

    def test_existing_ids_returns_only_matches(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        a = repo.insert(tool_name="gitleaks", name="a", args=[])
        b = repo.insert(tool_name="gitleaks", name="b", args=[])
        result = repo.existing_ids([a, b, 9999])
        assert sorted(result) == sorted([a, b])

    def test_existing_ids_empty_input_returns_empty(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        assert repo.existing_ids([]) == []

    def test_get_returns_none_for_missing_id(
        self, repo: ToolArgProfilesRepository
    ) -> None:
        assert repo.get(9999) is None
