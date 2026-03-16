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


# ---------------------------------------------------------------------------
# update_finding helpers
# ---------------------------------------------------------------------------

_VALID_UPDATE = {
    "confidence": "probable",
    "finding_type": "vulnerability",
    "severity": "high",
    "reasoning": "Code review confirms taint flow reaches sink.",
    "remediation": "Parameterise the query.",
    "attack_vector": "network",
    "call_stack": None,
    "strategy": "manual",
}


# ---------------------------------------------------------------------------
# AC1–3: enum validation
# ---------------------------------------------------------------------------


async def test_invalid_confidence_raises(store: SQLiteStore) -> None:
    _seed(store)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid confidence"):
        await findings.update_finding(
            fid, **{**_VALID_UPDATE, "confidence": "definitely"}
        )
    # DB row unchanged
    row = await findings.get_finding(fid)
    assert row["confidence"] == _BASE_FINDING["confidence"]


async def test_invalid_severity_raises(store: SQLiteStore) -> None:
    _seed(store)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid severity"):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "severity": "extreme"})
    row = await findings.get_finding(fid)
    assert row["severity"] == _BASE_FINDING["severity"]


async def test_invalid_finding_type_raises(store: SQLiteStore) -> None:
    _seed(store)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid finding_type"):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "finding_type": "ghost"})
    # DB row unchanged (finding still exists and was not updated)
    db_row = await findings.get_finding(fid)
    assert db_row["finding_type"] == [_BASE_FINDING["finding_type"]]


# ---------------------------------------------------------------------------
# AC4: valid update
# ---------------------------------------------------------------------------


async def test_valid_update_returns_true_and_persists(
    store: SQLiteStore,
) -> None:
    _seed(store)
    fid = _first_id(store)
    result = await findings.update_finding(fid, **_VALID_UPDATE)
    assert result is True

    with store._connect() as conn:  # noqa: SLF001
        db_row = conn.execute("SELECT * FROM findings WHERE id = ?", (fid,)).fetchone()

    assert db_row["confidence"] == "probable"
    assert db_row["severity"] == "high"
    assert db_row["enriched"] == 1
    assert db_row["triaged_by"] == "claude-code"
    assert db_row["triaged_at"] is not None

    import json as _json

    ft = _json.loads(db_row["finding_type"])
    assert isinstance(ft, list)
    assert ft == ["vulnerability"]

    meta = _json.loads(db_row["meta"])
    triage = meta["triage"]
    assert triage["confidence"] == "probable"
    assert triage["strategy"] == "manual"
    assert triage["triaged_by"] == "claude-code"
    assert "triaged_at" in triage


# ---------------------------------------------------------------------------
# AC5: false_positive is a valid confidence level
# ---------------------------------------------------------------------------


async def test_false_positive_confidence_accepted(
    store: SQLiteStore,
) -> None:
    _seed(store)
    fid = _first_id(store)
    result = await findings.update_finding(
        fid, **{**_VALID_UPDATE, "confidence": "false_positive"}
    )
    assert result is True
    row = await findings.get_finding(fid)
    assert row["confidence"] == "false_positive"


# ---------------------------------------------------------------------------
# AC6: not-found
# ---------------------------------------------------------------------------


async def test_nonexistent_finding_id_raises(store: SQLiteStore) -> None:
    with pytest.raises(ValueError, match="not found"):
        await findings.update_finding(999_999, **_VALID_UPDATE)


# ---------------------------------------------------------------------------
# AC7: batch with mix of valid and invalid
# ---------------------------------------------------------------------------


async def test_update_findings_batch_mixed(store: SQLiteStore) -> None:
    run_id = store.create_run({})
    store.upsert_findings(
        run_id,
        [
            {**_BASE_FINDING, "rule_id": "rule-a", "file_path": "src/a.py"},
            {**_BASE_FINDING, "rule_id": "rule-b", "file_path": "src/b.py"},
        ],
    )
    with store._connect() as conn:  # noqa: SLF001
        ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
        ]
    fid_valid, fid_bad = ids[0], ids[1]

    updates = [
        {"finding_id": fid_valid, **_VALID_UPDATE},
        {"finding_id": fid_bad, **{**_VALID_UPDATE, "confidence": "bogus"}},
    ]
    result = await findings.update_findings_batch(updates)

    assert result[fid_valid] is True
    assert result[fid_bad] is False

    # Valid one was actually updated
    row = await findings.get_finding(fid_valid)
    assert row["confidence"] == "probable"


# ---------------------------------------------------------------------------
# AC8: audit log written after every call
# ---------------------------------------------------------------------------


async def test_audit_written_on_success(store: SQLiteStore) -> None:
    _seed(store)
    fid = _first_id(store)
    await findings.update_finding(fid, **_VALID_UPDATE)

    with store._connect() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT tool_name, success, duration_ms FROM tool_audit_log"
            " WHERE tool_name = 'update_finding'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["success"] == 1
    assert row["duration_ms"] >= 0


async def test_audit_written_on_validation_failure(
    store: SQLiteStore,
) -> None:
    _seed(store)
    fid = _first_id(store)
    with pytest.raises(ValueError):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "severity": "unknown"})

    with store._connect() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT success FROM tool_audit_log"
            " WHERE tool_name = 'update_finding'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["success"] == 0


# ---------------------------------------------------------------------------
# AC9: previous_confidence tracks the prior value
# ---------------------------------------------------------------------------


async def test_previous_confidence_tracked_across_updates(
    store: SQLiteStore,
) -> None:
    _seed(store)  # initial confidence = "medium"
    fid = _first_id(store)

    # First update: medium → probable
    await findings.update_finding(fid, **{**_VALID_UPDATE, "confidence": "probable"})
    # Second update: probable → confirmed
    await findings.update_finding(fid, **{**_VALID_UPDATE, "confidence": "confirmed"})

    with store._connect() as conn:  # noqa: SLF001
        db_row = conn.execute(
            "SELECT meta FROM findings WHERE id = ?", (fid,)
        ).fetchone()
    import json as _json

    meta = _json.loads(db_row["meta"])
    assert meta["triage"]["previous_confidence"] == "probable"
    assert meta["triage"]["confidence"] == "confirmed"
