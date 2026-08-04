"""Tests for FindingRepository.update_finding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from domain.findings.normalization import (  # noqa: E402
    build_triage_meta,
    normalise_finding_type,
    severity_to_rank,
)
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from tests.finding_helpers import normalize_test_findings  # noqa: E402

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
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))
    return run_id


class TestUpdateFinding:
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

        result = repo.update_finding(
            fid,
            severity_rank=severity_to_rank("high") or 0,
            confidence="probable",
            finding_type_json=normalise_finding_type("vulnerability") or "[]",
            triage_meta=build_triage_meta(
                "probable",
                "Code review confirms taint flow.",
                "Parameterize the query.",
                "network",
                None,
            ),
            strategy="manual",
            triaged_by="auto_triage",
            source="auto_triage",
        )
        assert result is True

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT confidence, severity, triaged_by FROM findings WHERE id = ?",
                (fid,),
            ).fetchone()
        assert row["confidence"] == "probable"
        assert row["severity"] == 1
        assert row["triaged_by"] == "auto_triage"

    def test_raises_for_missing_id(self, repo: FindingRepository) -> None:
        with pytest.raises(ValueError, match="not found"):
            repo.update_finding(
                999_999,
                severity_rank=severity_to_rank("high") or 0,
                confidence="probable",
                finding_type_json=normalise_finding_type("vulnerability") or "[]",
                triage_meta=build_triage_meta(
                    "probable",
                    "Code review confirms taint flow.",
                    "Parameterize the query.",
                    "network",
                    None,
                ),
                strategy="manual",
                triaged_by="auto_triage",
                source="auto_triage",
            )

    def test_triage_block_in_meta(
        self,
        factory: ConnectionFactory,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        _seed(run_repo, repo, [{"tool": "semgrep", "file_path": "a.py"}])
        with factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]

        repo.update_finding(
            fid,
            severity_rank=severity_to_rank("high") or 0,
            confidence="probable",
            finding_type_json=normalise_finding_type("vulnerability") or "[]",
            triage_meta=build_triage_meta(
                "probable",
                "Code review confirms taint flow.",
                "Parameterize the query.",
                "network",
                None,
            ),
            strategy="manual",
            triaged_by="auto_triage",
            source="auto_triage",
        )

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT meta FROM findings WHERE id = ?", (fid,)
            ).fetchone()
        meta = json.loads(row["meta"])
        triage = meta["triage"]
        assert triage["confidence"] == "probable"
        assert triage["strategy"] == "manual"
        assert triage["triaged_by"] == "auto_triage"
        assert triage["triage_provider"] is None
        assert "triaged_at" in triage
