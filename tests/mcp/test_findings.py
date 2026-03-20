"""Integration tests for mcp.tools.findings read tools."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.findings.updater import reconstruct_abs_path  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.audit import AuditRepository  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import TriageBatchRepository  # noqa: E402
from tally_mcp.context import FindingsContext  # noqa: E402
from tally_mcp.tools import findings  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "medium",
    "file_path": "src/app.py",
    "rule_id": "python.flask.sqli",
    "description": "SQL injection risk",
}


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    overrides: dict | None = None,
) -> None:
    finding = {**_BASE_FINDING, **(overrides or {})}
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, [finding])


def _first_id(factory: ConnectionFactory) -> int:
    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    assert row is not None
    return row["id"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(
        tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    )
    f.init_schema()
    return f


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def audit_repo(factory: ConnectionFactory) -> AuditRepository:
    return AuditRepository(factory)


@pytest.fixture()
def triage_repo(factory: ConnectionFactory) -> TriageBatchRepository:
    return TriageBatchRepository(factory)


# Convenience fixture that sets up all injections
@pytest.fixture()
def store(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
    triage_repo: TriageBatchRepository,
) -> ConnectionFactory:
    """Return factory with all repos injected into findings module."""
    findings.init(
        FindingsContext(
            finding_repo=finding_repo,
            audit_repo=audit_repo,
            triage_repo=triage_repo,
            project_name="",
        )
    )
    return factory


# ---------------------------------------------------------------------------
# get_finding tests
# ---------------------------------------------------------------------------


async def test_get_finding_returns_parsed_dict(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert isinstance(row, dict)
    assert isinstance(row["meta"], dict)
    assert isinstance(row["finding_type"], list)


async def test_get_finding_unknown_id_raises_value_error(
    store: ConnectionFactory,
    finding_repo: FindingRepository,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await findings.get_finding(999_999)


async def test_null_severity_confidence_returned_as_none(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
) -> None:
    _seed(run_repo, finding_repo, {"severity": None, "confidence": None})
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert row["severity"] is None
    assert row["confidence"] is None


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


async def test_invalid_confidence_raises(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid confidence"):
        await findings.update_finding(
            fid, **{**_VALID_UPDATE, "confidence": "definitely"}
        )
    # DB row unchanged
    row = await findings.get_finding(fid)
    assert row["confidence"] == _BASE_FINDING["confidence"]


async def test_invalid_severity_raises(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid severity"):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "severity": "extreme"})
    row = await findings.get_finding(fid)
    assert row["severity"] == _BASE_FINDING["severity"]


async def test_invalid_finding_type_raises(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid finding_type"):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "finding_type": "ghost"})
    db_row = await findings.get_finding(fid)
    assert db_row["finding_type"] == [_BASE_FINDING["finding_type"]]


# ---------------------------------------------------------------------------
# AC4: valid update
# ---------------------------------------------------------------------------


async def test_valid_update_returns_true_and_persists(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    result = await findings.update_finding(fid, **_VALID_UPDATE)
    assert result is True

    with store.connect() as conn:
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
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
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


async def test_nonexistent_finding_id_raises(
    store: ConnectionFactory,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await findings.update_finding(999_999, **_VALID_UPDATE)


# ---------------------------------------------------------------------------
# AC7: batch with mix of valid and invalid
# ---------------------------------------------------------------------------


async def test_update_findings_batch_mixed(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(
        run_id,
        [
            {**_BASE_FINDING, "rule_id": "rule-a", "file_path": "src/a.py"},
            {**_BASE_FINDING, "rule_id": "rule-b", "file_path": "src/b.py"},
        ],
    )
    with store.connect() as conn:
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

    assert result[str(fid_valid)]["status"] == "updated"
    assert result[str(fid_bad)]["status"] == "error"

    row = await findings.get_finding(fid_valid)
    assert row["confidence"] == "probable"


# ---------------------------------------------------------------------------
# AC8: audit log written after every call
# ---------------------------------------------------------------------------


async def test_audit_written_on_success(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    await findings.update_finding(fid, **_VALID_UPDATE)

    with store.connect() as conn:
        row = conn.execute(
            "SELECT tool_name, success, duration_ms FROM tool_audit_log"
            " WHERE tool_name = 'update_finding'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["success"] == 1
    assert row["duration_ms"] >= 0


async def test_audit_written_on_validation_failure(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "severity": "unknown"})

    with store.connect() as conn:
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
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)  # initial confidence = "medium"
    fid = _first_id(store)

    # First update: medium → probable
    await findings.update_finding(fid, **{**_VALID_UPDATE, "confidence": "probable"})
    # Second update: probable → confirmed
    await findings.update_finding(fid, **{**_VALID_UPDATE, "confidence": "confirmed"})

    with store.connect() as conn:
        db_row = conn.execute(
            "SELECT meta FROM findings WHERE id = ?", (fid,)
        ).fetchone()
    import json as _json

    meta = _json.loads(db_row["meta"])
    assert meta["triage"]["previous_confidence"] == "probable"
    assert meta["triage"]["confidence"] == "confirmed"


# ---------------------------------------------------------------------------
# _reconstruct_abs_path unit tests
# ---------------------------------------------------------------------------

_REPOS = [{"name": "myapp", "path": "/repos/myapp"}]


def test_reconstruct_abs_path_known_repo() -> None:
    result = reconstruct_abs_path("/src/app.py", "myapp", _REPOS)
    assert result == "/repos/myapp/src/app.py"


def test_reconstruct_abs_path_unknown_repo() -> None:
    result = reconstruct_abs_path("/src/app.py", "unknown", _REPOS)
    assert result is None


def test_reconstruct_abs_path_none_file() -> None:
    result = reconstruct_abs_path(None, "myapp", _REPOS)
    assert result is None


def test_reconstruct_abs_path_none_repo_name() -> None:
    result = reconstruct_abs_path("/src/app.py", None, _REPOS)
    assert result is None


def test_reconstruct_abs_path_trailing_slash_stripped() -> None:
    repos = [{"name": "myapp", "path": "/repos/myapp/"}]
    result = reconstruct_abs_path("/src/app.py", "myapp", repos)
    assert result == "/repos/myapp/src/app.py"


# ---------------------------------------------------------------------------
# get_finding includes abs_path
# ---------------------------------------------------------------------------


async def test_get_finding_includes_abs_path(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert "abs_path" in row


# ---------------------------------------------------------------------------
# TestAtomicBatchClaim
# ---------------------------------------------------------------------------


def _seed_batch(
    factory: ConnectionFactory,
    run_repo: RunRepository,
    status: str = "pending",
    attempts: int = 0,
) -> int:
    run_id = run_repo.create_run({})
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                json.dumps([1, 2]),
                json.dumps([{"id": 1}, {"id": 2}]),
                status,
                attempts,
            ),
        )
    return run_id


class TestAtomicBatchClaim:
    def test_claim_sets_in_progress_increments_attempts_sets_started_at(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        result = triage_repo.claim_batch(run_id)
        assert result is not None
        assert result["status"] == "in_progress"
        assert result["run_attempts"] == 1
        assert result["started_at"] is not None

    def test_two_concurrent_claims_no_duplication(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        results: list[dict | None] = [None, None]

        def _claim(idx: int) -> None:
            results[idx] = triage_repo.claim_batch(run_id)

        t1 = threading.Thread(target=_claim, args=(0,))
        t2 = threading.Thread(target=_claim, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1, "exactly one thread should have claimed the batch"

    def test_no_pending_batches_returns_none(
        self,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_id = run_repo.create_run({})
        result = triage_repo.claim_batch(run_id)
        assert result is None

    def test_exhausted_attempts_never_claimed(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="pending", attempts=3)
        result = triage_repo.claim_batch(run_id)
        assert result is None

    def test_complete_success_sets_status_and_completed_at(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = triage_repo.claim_batch(run_id)
        assert batch is not None

        triage_repo.complete_batch(batch["id"], "success")

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch["id"],),
            ).fetchone()
        assert row["status"] == "success"
        assert row["completed_at"] is not None

    def test_complete_failed_sets_status_and_completed_at(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = triage_repo.claim_batch(run_id)
        assert batch is not None

        triage_repo.complete_batch(batch["id"], "failed")

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch["id"],),
            ).fetchone()
        assert row["status"] == "failed"
        assert row["completed_at"] is not None

    def test_claim_scoped_to_correct_run_id(
        self,
        factory: ConnectionFactory,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
    ) -> None:
        run_a = run_repo.create_run({})
        run_b = _seed_batch(factory, run_repo)

        result = triage_repo.claim_batch(run_a)
        assert result is None

        result_b = triage_repo.claim_batch(run_b)
        assert result_b is not None
        assert result_b["run_id"] == run_b
