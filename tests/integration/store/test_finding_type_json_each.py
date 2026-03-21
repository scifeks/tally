"""Integration tests for finding_type json_each SQLite filter."""

from __future__ import annotations

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


def _make_store(
    tmp_path: Path,
) -> tuple[ConnectionFactory, RunRepository, FindingRepository]:
    factory = ConnectionFactory(
        tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    )
    factory.init_schema()
    return factory, RunRepository(factory), FindingRepository(factory)


class TestFindingTypeJsonEach:
    def test_exact_match_secret_does_not_return_vulnerability(
        self, tmp_path: Path
    ) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["finding_type"] == ["secret"] for r in results)
        assert not any(r["metadata"].get("tool") == "semgrep" for r in results)

    def test_exact_match_multi_value_returns_both_types(self, tmp_path: Path) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "=", ["secret", "vulnerability"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert "nmap" not in tools

    def test_partial_match_vuln_matches_vulnerability(self, tmp_path: Path) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "~=", ["vuln"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all(r["metadata"]["tool"] == "semgrep" for r in results)

    def test_exact_match_does_not_return_unrelated_type(self, tmp_path: Path) -> None:
        _, run_repo, finding_repo = _make_store(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(
            run_id,
            [
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                },
            ],
        )
        results = finding_repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert results == []
