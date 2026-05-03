"""Integration tests for ToolOverridesRepository."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.tool_overrides import (  # noqa: E402
    ToolOverrideNameConflict,
)
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.tool_overrides import (  # noqa: E402
    ToolOverridesRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> ToolOverridesRepository:
    return ToolOverridesRepository(factory)


class TestToolOverridesRepository:
    def test_insert_local_round_trip(self, repo: ToolOverridesRepository) -> None:
        rid = repo.insert(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/local/bin/semgrep",
        )
        row = repo.get_by_tool_name("semgrep")
        assert row is not None
        assert row.id == rid
        assert row.tool_name == "semgrep"
        assert row.args_mode == "stock"
        assert row.type == "repo"
        assert row.location == "local"
        assert row.path == "/usr/local/bin/semgrep"
        assert row.container_name is None
        assert row.container_tool_path is None

    def test_insert_docker_round_trip(self, repo: ToolOverridesRepository) -> None:
        rid = repo.insert(
            tool_name="gitleaks",
            args_mode="custom",
            type="repo",
            location="docker",
            container_name="gitleaks-runner",
            container_tool_path="/usr/bin/gitleaks",
        )
        row = repo.get_by_tool_name("gitleaks")
        assert row is not None
        assert row.id == rid
        assert row.args_mode == "custom"
        assert row.location == "docker"
        assert row.container_name == "gitleaks-runner"
        assert row.container_tool_path == "/usr/bin/gitleaks"
        assert row.path is None

    def test_insert_returns_lastrowid_as_integer(
        self, repo: ToolOverridesRepository
    ) -> None:
        rid = repo.insert(
            tool_name="x",
            args_mode="stock",
            type="repo",
            location="local",
            path="/x",
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_list_paginated_returns_rows_and_total(
        self, repo: ToolOverridesRepository
    ) -> None:
        for name in ("a", "b", "c"):
            repo.insert(
                tool_name=name,
                args_mode="stock",
                type="repo",
                location="local",
                path=f"/{name}",
            )
        rows, total = repo.list_paginated()
        assert total == 3
        assert {r.tool_name for r in rows} == {"a", "b", "c"}

    def test_list_paginated_respects_offset_and_limit(
        self, repo: ToolOverridesRepository
    ) -> None:
        ids = [
            repo.insert(
                tool_name=f"t{i}",
                args_mode="stock",
                type="repo",
                location="local",
                path=f"/t{i}",
            )
            for i in range(5)
        ]
        rows, total = repo.list_paginated(offset=1, limit=2)
        assert total == 5
        assert [r.id for r in rows] == ids[1:3]

    def test_list_paginated_orders_by_id_ascending(
        self, repo: ToolOverridesRepository
    ) -> None:
        ids = [
            repo.insert(
                tool_name=name,
                args_mode="stock",
                type="repo",
                location="local",
                path=f"/{name}",
            )
            for name in ("zeta", "alpha", "mu")
        ]
        rows, _ = repo.list_paginated()
        assert [r.id for r in rows] == ids

    def test_get_by_tool_name_returns_none_for_missing(
        self, repo: ToolOverridesRepository
    ) -> None:
        assert repo.get_by_tool_name("never-inserted") is None

    def test_update_replaces_fields_and_bumps_updated_at(
        self, repo: ToolOverridesRepository
    ) -> None:
        repo.insert(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/old",
        )
        before = repo.get_by_tool_name("semgrep")
        assert before is not None
        repo.update(
            "semgrep",
            args_mode="custom",
            type="repo",
            location="local",
            path="/new",
        )
        after = repo.get_by_tool_name("semgrep")
        assert after is not None
        assert after.args_mode == "custom"
        assert after.path == "/new"
        assert after.updated_at >= before.updated_at
        assert after.created_at == before.created_at

    def test_update_swap_location_local_to_docker_clears_path(
        self, repo: ToolOverridesRepository
    ) -> None:
        repo.insert(
            tool_name="zap",
            args_mode="stock",
            type="api",
            location="local",
            path="/usr/bin/zap",
        )
        repo.update(
            "zap",
            args_mode="stock",
            type="api",
            location="docker",
            container_name="zap-runner",
            container_tool_path="/zap/zap.sh",
        )
        row = repo.get_by_tool_name("zap")
        assert row is not None
        assert row.location == "docker"
        assert row.path is None
        assert row.container_name == "zap-runner"
        assert row.container_tool_path == "/zap/zap.sh"

    def test_update_silent_when_tool_name_missing(
        self, repo: ToolOverridesRepository
    ) -> None:
        repo.update(
            "nonexistent",
            args_mode="stock",
            type="repo",
            location="local",
            path="/x",
        )
        assert repo.get_by_tool_name("nonexistent") is None

    def test_delete_removes_row(self, repo: ToolOverridesRepository) -> None:
        repo.insert(
            tool_name="x",
            args_mode="stock",
            type="repo",
            location="local",
            path="/x",
        )
        repo.delete("x")
        assert repo.get_by_tool_name("x") is None

    def test_delete_silent_when_tool_name_missing(
        self, repo: ToolOverridesRepository
    ) -> None:
        repo.delete("nonexistent")

    def test_delete_unconstrained_when_saved_scan_references_tool_name(
        self,
        repo: ToolOverridesRepository,
        factory: ConnectionFactory,
    ) -> None:
        repo.insert(
            tool_name="semgrep",
            args_mode="custom",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
        )
        with factory.connect() as conn:
            scan_cur = conn.execute(
                "INSERT INTO saved_scans (name) VALUES (?)", ("weekly",)
            )
            conn.execute(
                "INSERT INTO saved_scan_tools (saved_scan_id, tool_name) VALUES (?, ?)",
                (scan_cur.lastrowid, "semgrep"),
            )
        repo.delete("semgrep")
        assert repo.get_by_tool_name("semgrep") is None

    def test_unique_tool_name_raises_conflict_on_insert(
        self, repo: ToolOverridesRepository
    ) -> None:
        repo.insert(
            tool_name="dup",
            args_mode="stock",
            type="repo",
            location="local",
            path="/dup",
        )
        with pytest.raises(ToolOverrideNameConflict) as excinfo:
            repo.insert(
                tool_name="dup",
                args_mode="stock",
                type="repo",
                location="local",
                path="/dup-2",
            )
        assert excinfo.value.tool_name == "dup"
