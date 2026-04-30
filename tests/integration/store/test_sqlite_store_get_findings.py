"""Integration tests for SQLite store get_findings method."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.store import make_store
from infrastructure.store.connection import ConnectionFactory

pytestmark = pytest.mark.integration

_PROJECT_NAME = "test-proj"


class _TestStore:
    """Thin wrapper that exposes a SQLiteStore-compatible surface for tests."""

    def __init__(
        self, factory: ConnectionFactory, run_repo: object, finding_repo: object
    ) -> None:
        self._factory = factory
        self._run_repo = run_repo
        self._finding_repo = finding_repo
        self._db_path = factory.db_path

    def create_run(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._run_repo.create_run(*args, **kwargs)  # type: ignore[attr-defined]

    def insert_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.insert_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.search(*args, **kwargs)  # type: ignore[attr-defined]

    def get_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.get_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def count_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.count_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def delete_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.delete_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def get_tool_meta_keys(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.get_tool_meta_keys(*args, **kwargs)  # type: ignore[attr-defined]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        self._factory.init_schema()


def _make_store(tmp_path: Path) -> _TestStore:
    run_repo, finding_repo, _, _ = make_store(tmp_path, _PROJECT_NAME)
    factory = ConnectionFactory(
        tmp_path / "projects" / _PROJECT_NAME / "sqlite" / "findings.db"
    )
    return _TestStore(factory, run_repo, finding_repo)


_SAST_FINDING = {
    "tool": "semgrep",
    "domain": "code",
    "segment": "sast",
    "finding_type": "vulnerability",
    "severity": "high",
    "file_path": "src/app.py",
    "rule_id": "python.sqli",
}

_SECRETS_FINDING = {
    "tool": "gitleaks",
    "domain": "code",
    "segment": "secrets",
    "finding_type": "secret",
    "severity": "critical",
    "file_path": "config.py",
    "rule_id": "generic-api-key",
}

_SCA_FINDING_GF = {
    "tool": "pip-audit",
    "domain": "sca",
    "segment": "sca",
    "finding_type": "dependency",
    "severity": "high",
    "package_name": "requests",
    "vulnerability_id": "GHSA-abc",
    "ecosystem": "PyPI",
    "lockfile": "requirements.txt",
}

_NO_FILE_FINDING = {
    "tool": "semgrep",
    "domain": "code",
    "segment": "sast",
    "finding_type": "vulnerability",
    "severity": "medium",
    "rule_id": "python.xss",
}


def _seed_gf(store: _TestStore) -> None:
    run_id = store.create_run({})
    store.insert_findings(
        run_id,
        [_SAST_FINDING, _SECRETS_FINDING, _SCA_FINDING_GF, _NO_FILE_FINDING],
    )


class TestGetFindings:
    def test_get_findings_segment_filter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        rows = store.get_findings(segments=["sast"], limit=100)
        assert all(r["segment"] == "sast" for r in rows)
        assert len(rows) >= 1

    def test_get_findings_no_segment_filter_returns_all(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        rows = store.get_findings(segments=None, limit=100)
        segments = {r["segment"] for r in rows}
        assert "sast" in segments
        assert "secrets" in segments

    def test_get_findings_require_file_excludes_nulls(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        rows = store.get_findings(require_file=True, limit=100)
        assert all(r["file"] for r in rows)

    def test_get_findings_require_file_false_includes_nulls(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        rows = store.get_findings(require_file=False, limit=100)
        null_file_rows = [r for r in rows if not r["file"]]
        assert len(null_file_rows) >= 1

    def test_get_findings_repo_equality(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        with store._connect() as conn:
            cur1 = conn.execute(
                "INSERT INTO repositories (name) VALUES (?)",
                ("myrepo",),
            )
            myrepo_id = cur1.lastrowid
            cur2 = conn.execute(
                "INSERT INTO repositories (name) VALUES (?)",
                ("otherrepo",),
            )
            otherrepo_id = cur2.lastrowid
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [
                {**_SAST_FINDING, "repo_id": myrepo_id},
                {**_SAST_FINDING, "repo_id": otherrepo_id, "rule_id": "r2"},
            ],
        )
        rows = store.get_findings(limit=100)
        myrepo_rows = [r for r in rows if r["repo_id"] == myrepo_id]
        assert len(myrepo_rows) == 1
        assert myrepo_rows[0]["repo_id"] == myrepo_id

    def test_get_findings_status_filter(self, tmp_path: Path) -> None:
        """get_findings(status=...) returns only findings with that status."""
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [
                {"tool": "semgrep", "severity": "high"},
                {"tool": "gitleaks", "severity": "critical"},
            ],
        )
        with store._connect() as conn:
            conn.execute("UPDATE findings SET status='triaged' WHERE tool='semgrep'")
        rows = store.get_findings(status="triaged", limit=100)
        assert len(rows) >= 1
        assert all(r["status"] == "triaged" for r in rows)
        rows_active = store.get_findings(status="active", limit=100)
        for r in rows_active:
            assert r["status"] != "triaged"

    def test_get_findings_domain_filter(self, tmp_path: Path) -> None:
        """get_findings(domain=...) returns only findings with that domain."""
        store = _make_store(tmp_path)
        _seed_gf(store)
        rows = store.get_findings(domain="sca", limit=100)
        assert len(rows) >= 1
        assert all(r["domain"] == "sca" for r in rows)
        rows_code = store.get_findings(domain="code", limit=100)
        assert len(rows_code) >= 1
        assert all(r["domain"] == "code" for r in rows_code)

    def test_get_findings_combined_filters(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [
                {**_SAST_FINDING},
                {**_SECRETS_FINDING},
                {**_SCA_FINDING_GF},
                {**_NO_FILE_FINDING},
            ],
        )
        rows = store.get_findings(
            tools=["semgrep"],
            segments=["sast", "sca", "api"],
            require_file=True,
            limit=100,
        )
        assert all(r["tool"] == "semgrep" for r in rows)
        assert all(r["segment"] in ("sast", "sca", "api") for r in rows)
        assert all(r["file"] for r in rows)


class TestPagination:
    def test_limit_caps_rows(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [{**_SAST_FINDING, "rule_id": f"rule-{i}"} for i in range(5)],
        )
        rows = store.get_findings(limit=3)
        assert len(rows) == 3

    def test_offset_skips_rows(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [{**_SAST_FINDING, "rule_id": f"rule-{i}"} for i in range(5)],
        )
        all_rows = store.get_findings(limit=100, offset=0)
        offset_rows = store.get_findings(limit=100, offset=2)
        assert len(offset_rows) == len(all_rows) - 2
        assert [r["id"] for r in offset_rows] == [r["id"] for r in all_rows[2:]]

    def test_order_is_stable_id_desc(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [{**_SAST_FINDING, "rule_id": f"rule-{i}"} for i in range(4)],
        )
        rows_a = store.get_findings(limit=100)
        rows_b = store.get_findings(limit=100)
        assert [r["id"] for r in rows_a] == [r["id"] for r in rows_b]
        ids = [r["id"] for r in rows_a]
        assert ids == sorted(ids, reverse=True)

    def test_count_findings_matches_total(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        total = store.count_findings()
        rows = store.get_findings(limit=1000)
        assert total == len(rows)

    def test_count_findings_with_filter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        total_sast = store.count_findings(segments=["sast"])
        rows_sast = store.get_findings(segments=["sast"], limit=1000)
        assert total_sast == len(rows_sast)

    def test_count_findings_ignores_pagination(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [{**_SAST_FINDING, "rule_id": f"rule-{i}"} for i in range(6)],
        )
        total = store.count_findings()
        page1 = store.get_findings(limit=2, offset=0)
        page2 = store.get_findings(limit=2, offset=2)
        page3 = store.get_findings(limit=2, offset=4)
        assert len(page1) + len(page2) + len(page3) == total

    def test_paginated_slices_sum_to_total(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_gf(store)
        total = store.count_findings()
        collected: list[int] = []
        offset = 0
        page_size = 2
        while True:
            rows = store.get_findings(limit=page_size, offset=offset)
            if not rows:
                break
            collected.extend(r["id"] for r in rows)
            offset += page_size
        assert len(collected) == total
        assert len(set(collected)) == total
