"""Integration tests for mcp.tools.findings read tools."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.store.sqlite_store import SQLiteStore  # noqa: E402
from mcp.config import MAX_BATCH_SIZE  # noqa: E402
from mcp.tools import findings  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "medium",
    "file_path": "src/app.py",
    "rule_id": "python.flask.sqli",
    "description": "SQL injection risk",
}


def _seed(store: SQLiteStore, overrides: dict | None = None) -> None:
    finding = {**_BASE_FINDING, **(overrides or {})}
    run_id = store.create_run({})
    store.upsert_findings(run_id, [finding])


def _first_id(store: SQLiteStore) -> int:
    with store._connect() as conn:  # noqa: SLF001
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    assert row is not None
    return row["id"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> SQLiteStore:
    s = SQLiteStore(tmp_path, "testproject")
    findings._store = s
    return s


# ---------------------------------------------------------------------------
# get_finding tests
# ---------------------------------------------------------------------------


async def test_get_finding_returns_parsed_dict(store: SQLiteStore) -> None:
    _seed(store)
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert isinstance(row, dict)
    assert isinstance(row["meta"], dict)
    assert isinstance(row["finding_type"], list)


async def test_get_finding_unknown_id_raises_value_error(
    store: SQLiteStore,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await findings.get_finding(999_999)


async def test_null_severity_confidence_returned_as_none(
    store: SQLiteStore,
) -> None:
    _seed(store, {"severity": None, "confidence": None})
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert row["severity"] is None
    assert row["confidence"] is None


# ---------------------------------------------------------------------------
# get_findings_batch tests
# ---------------------------------------------------------------------------


async def test_get_findings_batch_returns_sorted(store: SQLiteStore) -> None:
    run_id = store.create_run({})
    store.upsert_findings(
        run_id,
        [
            {**_BASE_FINDING, "file_path": "src/z.py", "line_start": 10},
            {**_BASE_FINDING, "file_path": "src/a.py", "line_start": 5},
            {**_BASE_FINDING, "file_path": "src/a.py", "line_start": 1},
        ],
    )
    rows = await findings.get_findings_batch("testproject")
    files = [r.get("file") or "" for r in rows]
    assert files == sorted(files)
    a_rows = [r for r in rows if r.get("file") == "src/a.py"]
    lines = [(r.get("meta") or {}).get("line_start") or 0 for r in a_rows]
    assert lines == sorted(lines)


async def test_get_findings_batch_tool_filter(store: SQLiteStore) -> None:
    run_id = store.create_run({})
    store.upsert_findings(
        run_id,
        [
            {**_BASE_FINDING, "tool": "semgrep"},
            {
                "tool": "gitleaks",
                "domain": "secrets",
                "finding_type": "secret",
                "severity": "critical",
                "file_path": ".env",
                "rule_id": "aws-key",
                "description": "AWS key",
            },
        ],
    )
    rows = await findings.get_findings_batch("testproject", tools=["semgrep"])
    assert all(r["tool"] == "semgrep" for r in rows)
    assert len(rows) >= 1


async def test_get_findings_batch_domain_filter(store: SQLiteStore) -> None:
    run_id = store.create_run({})
    store.upsert_findings(
        run_id,
        [
            {**_BASE_FINDING, "domain": "sast"},
            {**_BASE_FINDING, "domain": "secrets", "rule_id": "other-rule"},
        ],
    )
    rows = await findings.get_findings_batch("testproject", domain="sast")
    assert all(r["domain"] == "sast" for r in rows)


async def test_get_findings_batch_respects_max_batch_size(
    store: SQLiteStore,
) -> None:
    run_id = store.create_run({})
    n = MAX_BATCH_SIZE + 5
    batch = [
        {**_BASE_FINDING, "rule_id": f"rule-{i}", "file_path": f"src/f{i}.py"}
        for i in range(n)
    ]
    store.upsert_findings(run_id, batch)
    rows = await findings.get_findings_batch("testproject")
    assert len(rows) <= MAX_BATCH_SIZE


async def test_get_findings_batch_timeout_returns_empty(
    store: SQLiteStore,
) -> None:
    _seed(store)
    with patch(
        "mcp.tools.findings.asyncio.wait_for",
        side_effect=TimeoutError,
    ):
        rows = await findings.get_findings_batch("testproject")

    assert rows == []
    # Audit row must be written with success=0
    with store._connect() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT success, error FROM tool_audit_log"
            " WHERE tool_name = 'get_findings_batch'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["success"] == 0
    assert row["error"] == "timeout"
