"""Integration tests for the SQLite structured findings store.

Run from the tally project root::

    pytest tests/validation/test_sqlite_store.py -v
    pytest tests/store/ -v

No external dependencies (no Ollama, no ChromaDB).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.store.sqlite_store import SQLiteStore  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_PROJECT_NAME = "test-proj"


def _make_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path, _PROJECT_NAME)
    store._init_schema()
    return store


# Reusable seed datasets
_SEMGREP_FINDINGS = [
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "high",
        "confidence": "probable",
        "file_path": "config/app.py",
        "rule_id": "python.sql-injection",
        "line_start": 42,
        "profile": "repo1",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "medium",
        "confidence": "potential",
        "file_path": "web/index.php",
        "rule_id": "php.xss",
        "line_start": 10,
        "profile": "repo1",
    },
]

_GITLEAKS_FINDINGS = [
    {
        "tool": "gitleaks",
        "domain": "code",
        "finding_type": "secret",
        "severity": "critical",
        "confidence": "confirmed",
        "file_path": "src/config.py",
        "rule_id": "generic-api-key",
        "line_number": 99,
        "profile": "repo1",
    },
    {
        "tool": "gitleaks",
        "domain": "code",
        "finding_type": "secret",
        "severity": "high",
        "confidence": "confirmed",
        "file_path": "deploy/setup.sh",
        "rule_id": "aws-access-key",
        "line_number": 5,
        "profile": "repo1",
    },
]

_NMAP_FINDINGS = [
    {
        "tool": "nmap",
        "domain": "network",
        "finding_type": "informational",
        "severity": "informational",
        "confidence": "confirmed",
        "ip_address": "192.168.1.1",
        "port": "22",
        "service": "ssh",
        "transport": "tcp",
        "profile": "production",
    },
]

_ZAP_FINDINGS = [
    {
        "tool": "zap",
        "domain": "web",
        "finding_type": "vulnerability",
        "severity": "high",
        "confidence": "probable",
        "url": "https://example.com/login",
        "method": "POST",
        "param": "user_id",
        "alert_name": "sql_injection",
        "risk_type": "sql_injection",
        "profile": "repo1",
    },
    {
        "tool": "zap",
        "domain": "web",
        "finding_type": "vulnerability",
        "severity": "medium",
        "confidence": "probable",
        "url": "https://example.com/search",
        "method": "GET",
        "param": "q",
        "alert_name": "xss_reflected",
        "risk_type": "xss_reflected",
        "profile": "repo1",
    },
]


def _seed_all(store: SQLiteStore) -> int:
    run_id = store.create_run({"args": []})
    all_findings = (
        _SEMGREP_FINDINGS + _GITLEAKS_FINDINGS + _NMAP_FINDINGS + _ZAP_FINDINGS
    )
    store.upsert_findings(run_id, all_findings)
    return run_id


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


class TestBasicRoundTrip:
    def test_upsert_and_query_all(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS)

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert len(results) == len(_SEMGREP_FINDINGS)

    def test_result_has_metadata_and_distance(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS[:1])

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        r = results[0]
        assert "metadata" in r
        assert r["distance"] is None

    def test_metadata_tool_field(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS[:1])

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"]["tool"] == "semgrep"

    def test_file_path_remapped(self, tmp_path: Path) -> None:
        """SQLite column 'file' is returned as 'file_path' in metadata."""
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS[:1])

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert "file_path" in results[0]["metadata"]
        assert "file" not in results[0]["metadata"]

    def test_ip_address_remapped(self, tmp_path: Path) -> None:
        """SQLite column 'host' is returned as 'ip_address' in metadata."""
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _NMAP_FINDINGS)

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert "ip_address" in results[0]["metadata"]
        assert "host" not in results[0]["metadata"]

    def test_enriched_set_to_true(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _GITLEAKS_FINDINGS[:1])

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"]["enriched"] is True


# ---------------------------------------------------------------------------
# Tool filter
# ---------------------------------------------------------------------------


class TestToolFilter:
    def test_single_tool_filter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        results = store.search(
            {
                "conditions": [("tool", "=", ["semgrep"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["tool"] == "semgrep" for r in results)
        assert len(results) == len(_SEMGREP_FINDINGS)

    def test_multi_tool_csv_filter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        results = store.search(
            {
                "conditions": [("tool", "=", ["semgrep", "gitleaks"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert tools == {"semgrep", "gitleaks"}
        assert len(results) == len(_SEMGREP_FINDINGS) + len(_GITLEAKS_FINDINGS)

    def test_no_bleed_from_other_tools(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        results = store.search(
            {
                "conditions": [("tool", "=", ["nmap"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["tool"] == "nmap" for r in results)


# ---------------------------------------------------------------------------
# Exact match vs. partial match
# ---------------------------------------------------------------------------


class TestExactVsPartial:
    def test_exact_match_does_not_return_partial(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS)

        # "high" should not return "medium"
        results = store.search(
            {
                "conditions": [("severity", "=", ["high"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["severity"] == "high" for r in results)
        assert not any(r["metadata"]["severity"] == "medium" for r in results)

    def test_contains_returns_substring_match(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS)

        # "sql" should match "python.sql-injection"
        results = store.search(
            {
                "conditions": [("rule_id", "~=", ["sql"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert any("sql" in r["metadata"]["rule_id"] for r in results)


# ---------------------------------------------------------------------------
# File filter
# ---------------------------------------------------------------------------


class TestFileFilter:
    def test_file_contains_config(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        results = store.search(
            {
                "conditions": [("file", "~=", ["config"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all("config" in r["metadata"]["file_path"] for r in results)

    def test_file_contains_php_extension(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _SEMGREP_FINDINGS)

        results = store.search(
            {
                "conditions": [("file", "~=", [".php"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all(".php" in r["metadata"]["file_path"] for r in results)


# ---------------------------------------------------------------------------
# Severity CSV filter
# ---------------------------------------------------------------------------


class TestSeverityFilter:
    def test_severity_csv_returns_both(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        results = store.search(
            {
                "conditions": [("severity", "=", ["high", "critical"])],
                "page": 1,
                "page_size": 200,
            }
        )
        sevs = {r["metadata"]["severity"] for r in results}
        assert "high" in sevs
        assert "critical" in sevs
        assert "medium" not in sevs
        assert "informational" not in sevs


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_page_two_returns_correct_slice(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        # Seed 7 findings (2 semgrep + 2 gitleaks + 1 nmap + 2 zap)
        store.upsert_findings(
            run_id,
            _SEMGREP_FINDINGS + _GITLEAKS_FINDINGS + _NMAP_FINDINGS + _ZAP_FINDINGS,
        )

        page1 = store.search({"conditions": [], "page": 1, "page_size": 5})
        page2 = store.search({"conditions": [], "page": 2, "page_size": 5})

        assert len(page1) == 5
        # Total = 7, so page 2 has 2 rows
        assert len(page2) == 2

    def test_page_one_and_two_no_overlap(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(
            run_id,
            _SEMGREP_FINDINGS + _GITLEAKS_FINDINGS + _NMAP_FINDINGS + _ZAP_FINDINGS,
        )

        p1_rules = [
            r["metadata"].get("rule_id")
            for r in store.search({"conditions": [], "page": 1, "page_size": 4})
        ]
        p2_rules = [
            r["metadata"].get("rule_id")
            for r in store.search({"conditions": [], "page": 2, "page_size": 4})
        ]
        # No row should appear in both pages
        assert not set(p1_rules) & set(p2_rules)

    def test_empty_second_page(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _NMAP_FINDINGS)

        page2 = store.search({"conditions": [], "page": 2, "page_size": 200})
        assert page2 == []


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


class TestPurge:
    def test_purge_all_clears_findings(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=None)

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results == []

    def test_purge_all_clears_runs(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=None)

        conn = store._connect()
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0

    def test_purge_tool_only_removes_that_tool(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=["semgrep"])

        remaining = store.search({"conditions": [], "page": 1, "page_size": 200})
        tools = {r["metadata"]["tool"] for r in remaining}
        assert "semgrep" not in tools
        assert "gitleaks" in tools
        assert "nmap" in tools

    def test_purge_tool_keeps_runs(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=["gitleaks"])

        conn = store._connect()
        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count >= 1

    def test_schema_recreated_after_db_delete(self, tmp_path: Path) -> None:
        """After deleting and recreating the DB, _init_schema works cleanly."""
        store = _make_store(tmp_path)
        _seed_all(store)

        # Simulate full purge: delete file then reinit
        store._db_path.unlink()
        store._init_schema()

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results == []


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_fingerprint_stability(self, tmp_path: Path) -> None:
        """Same finding with two different run_ids produces one row."""
        store = _make_store(tmp_path)

        run_id1 = store.create_run({"args": []})
        store.upsert_findings(run_id1, _GITLEAKS_FINDINGS[:1])

        run_id2 = store.create_run({"args": []})
        store.upsert_findings(run_id2, _GITLEAKS_FINDINGS[:1])

        conn = store._connect()
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 1  # ON CONFLICT deduplicates

    def test_fingerprint_uniqueness(self, tmp_path: Path) -> None:
        """Two different findings produce different fingerprints."""
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _GITLEAKS_FINDINGS)  # 2 findings

        conn = store._connect()
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 2


# ---------------------------------------------------------------------------
# Comma-joined list fields stored as JSON arrays
# ---------------------------------------------------------------------------


class TestMetaListFields:
    def test_comma_list_stored_as_json_array(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(
            run_id,
            [
                {
                    "tool": "semgrep",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_start": 1,
                    # Comma-joined string as stored by ChromaDB ingestor
                    "technology": "python, flask",
                    "references": "https://cwe.mitre.org, https://owasp.org",
                }
            ],
        )
        conn = store._connect()
        row = conn.execute("SELECT meta FROM findings").fetchone()
        meta = json.loads(row[0])
        assert isinstance(meta["technology"], list)
        assert "python" in meta["technology"]
        assert isinstance(meta["references"], list)
        assert len(meta["references"]) == 2


# ---------------------------------------------------------------------------
# JSON extract meta query (ZAP param filter)
# ---------------------------------------------------------------------------


class TestMetaJsonExtract:
    def test_param_contains_id(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(run_id, _ZAP_FINDINGS)

        results = store.search(
            {
                "conditions": [("json_extract(meta, '$.param')", "~=", ["id"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        # user_id contains "id"
        assert any("id" in r["metadata"].get("param", "") for r in results)

    def test_profile_exact_match(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        results = store.search(
            {
                "conditions": [
                    ("json_extract(meta, '$.profile')", "=", ["production"])
                ],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all(r["metadata"].get("profile") == "production" for r in results)
