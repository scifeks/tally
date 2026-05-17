"""Integration tests for SQLite store D2 finding_type json_each filter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.store import make_store
from infrastructure.store.connection import ConnectionFactory
from tests.finding_helpers import normalize_test_findings

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


_VULN_FINDING = {
    "tool": "semgrep",
    "domain": "code",
    "finding_type": "vulnerability",
    "severity": "high",
    "file_path": "app.py",
    "rule_id": "r-vuln",
    "line_start": 1,
}

_SECRET_FINDING = {
    "tool": "gitleaks",
    "domain": "code",
    "finding_type": "secret",
    "severity": "critical",
    "file_path": "config.py",
    "rule_id": "r-secret",
    "line_number": 10,
}

_DEP_FINDING = {
    "tool": "pip-audit",
    "domain": "sca",
    "finding_type": "dependency",
    "severity": "high",
    "package_name": "requests",
    "vulnerability_id": "GHSA-x",
    "ecosystem": "PyPI",
}

_MULTI_TYPE_FINDING = {
    "tool": "semgrep",
    "domain": "code",
    "finding_type": '["vulnerability", "dependency"]',
    "severity": "medium",
    "file_path": "mix.py",
    "rule_id": "r-multi",
    "line_start": 5,
}


def _seed_d2(store: _TestStore) -> None:
    run_id = store.create_run({})
    store.insert_findings(
        run_id,
        normalize_test_findings(
            [_VULN_FINDING, _SECRET_FINDING, _DEP_FINDING, _MULTI_TYPE_FINDING]
        ),
    )


class TestD2FindingTypeFilter:
    def test_type_vulnerability_matches_vuln_findings(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "=", ["vulnerability"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert "semgrep" in tools
        assert "gitleaks" not in tools
        assert "pip-audit" not in tools

    def test_type_dependency_matches_dep_findings(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "=", ["dependency"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert "pip-audit" in tools
        assert "gitleaks" not in tools

    def test_type_contains_vuln_matches_vulnerability(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "~=", ["vuln"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        for r in results:
            ft = r["metadata"].get("finding_type", [])
            assert any("vuln" in v for v in ft)

    def test_type_contains_dep_matches_dependency(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "~=", ["dep"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        for r in results:
            ft = r["metadata"].get("finding_type", [])
            assert any("dep" in v for v in ft)

    def test_multi_type_finding_appears_for_vulnerability(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "=", ["vulnerability"])],
                "page": 1,
                "page_size": 200,
            }
        )
        rule_ids = {r["metadata"].get("rule_id") for r in results}
        assert "r-multi" in rule_ids

    def test_multi_type_finding_appears_for_dependency(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "=", ["dependency"])],
                "page": 1,
                "page_size": 200,
            }
        )
        rule_ids = {r["metadata"].get("rule_id") for r in results}
        assert "r-multi" in rule_ids

    def test_multi_type_finding_does_not_appear_for_secret(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings([_MULTI_TYPE_FINDING]))
        results = store.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert results == []

    def test_csv_type_returns_both_types_or_semantics(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_d2(store)
        results = store.search(
            {
                "conditions": [("finding_type", "=", ["vulnerability", "dependency"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert "semgrep" in tools
        assert "pip-audit" in tools
        assert "gitleaks" not in tools
