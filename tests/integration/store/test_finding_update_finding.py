"""Tests for FindingRepository.update_finding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
) -> int:
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, findings)
    return run_id


class TestUpdateFinding:
    _VALID_UPDATE = {
        "confidence": "probable",
        "finding_type": "vulnerability",
        "severity": "high",
        "reasoning": "Code review confirms taint flow.",
        "remediation": "Parameterise the query.",
        "attack_vector": "network",
        "call_stack": None,
        "strategy": "manual",
    }

    def test_updates_row(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {
                    "tool": "semgrep",
                    "severity": "medium",
                    "confidence": "potential",
                    "file_path": "a.py",
                }
            ],
        )
        with factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]

        result = repo.update_finding(fid, **self._VALID_UPDATE)
        assert result is True

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT confidence, severity, triaged_by FROM findings WHERE id = ?",
                (fid,),
            ).fetchone()
        assert row["confidence"] == "probable"
        assert row["severity"] == "high"
        assert row["triaged_by"] == "claude-code"

    def test_raises_for_missing_id(self, repo: FindingRepository) -> None:
        with pytest.raises(ValueError, match="not found"):
            repo.update_finding(999_999, **self._VALID_UPDATE)

    def test_triage_block_in_meta(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "file_path": "a.py"}])
        with factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]

        repo.update_finding(fid, **self._VALID_UPDATE)

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT meta FROM findings WHERE id = ?", (fid,)
            ).fetchone()
        meta = json.loads(row["meta"])
        triage = meta["triage"]
        assert triage["confidence"] == "probable"
        assert triage["strategy"] == "manual"
        assert triage["triaged_by"] == "claude-code"
        assert "triaged_at" in triage
