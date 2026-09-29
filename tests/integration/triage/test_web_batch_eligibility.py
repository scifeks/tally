"""Integration tests for web segment batch eligibility.

Verifies that fetch_active_findings_for_batching returns web
findings with the fields the DAST prompt renderer expects,
and that batching produces size-1 batches for web.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.batching import (  # noqa: E402
    batch_size_for_segment,
    compute_batches,
)
from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from infrastructure.store.repositories.findings import (  # noqa: E402
    FindingRepository,
)
from infrastructure.store.repositories.runs import (  # noqa: E402
    RunRepository,
)
from infrastructure.store.repositories.triage import (  # noqa: E402
    TriageBatchRepository,
)
from tests.finding_helpers import (  # noqa: E402
    normalize_test_findings,
)

pytestmark = pytest.mark.integration


def _make_repos(
    tmp_path: Path,
) -> tuple[
    ConnectionFactory,
    RunRepository,
    FindingRepository,
    TriageBatchRepository,
]:
    factory = ConnectionFactory(
        tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    )
    factory.init_schema()
    return (
        factory,
        RunRepository(factory),
        FindingRepository(factory),
        TriageBatchRepository(factory),
    )


def _seed_repo(factory: ConnectionFactory, name: str) -> int:
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            (name,),
        )
        return cur.lastrowid  # type: ignore[return-value]


def _seed_findings(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict[str, Any]],
    factory: ConnectionFactory,
) -> int:
    repo_ids: dict[str, int] = {}
    for f in findings:
        name = f.get("repo", "unknown")
        if name not in repo_ids:
            repo_ids[name] = _seed_repo(factory, name)
    findings = [{**f, "repo_id": repo_ids[f.get("repo", "unknown")]} for f in findings]
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))
    return run_id


def _make_zap_finding(
    repo: str = "myrepo",
    url: str = "https://example.com/login",
    severity: str = "high",
    alert_name: str = "SQL Injection",
    method: str = "POST",
    param: str = "id",
    attack: str = "' OR '1'='1",
    evidence: str = "SQL syntax error",
    risk_type: str = "SQL Injection",
) -> dict[str, Any]:
    return {
        "tool": "zap",
        "repo": repo,
        "segment": "web",
        "url": url,
        "severity": severity,
        "alert_name": alert_name,
        "method": method,
        "param": param,
        "attack": attack,
        "evidence": evidence,
        "risk_type": risk_type,
        "cwe_id": 89,
        "confidence": "high",
        "description": "SQL injection may be possible",
    }


def _make_burp_finding(
    repo: str = "myrepo",
    url: str = "https://example.com/search",
    severity: str = "high",
    alert_name: str = "Reflected XSS",
    method: str = "GET",
    evidence: str = "Request:\nGET /search?q=<script>",
    remediation: str = "Encode output",
    fingerprint_type: str = "REFLECTED_XSS",
    risk_type: str = "Cross-site scripting",
) -> dict[str, Any]:
    return {
        "tool": "burp",
        "repo": repo,
        "segment": "web",
        "url": url,
        "severity": severity,
        "alert_name": alert_name,
        "method": method,
        "evidence": evidence,
        "remediation": remediation,
        "fingerprint_type": fingerprint_type,
        "risk_type": risk_type,
        "confidence": "confirmed",
        "description": "User input reflected without encoding",
    }


class TestWebBatchEligibility:
    def test_zap_findings_returned(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = _seed_findings(
            run_repo,
            finding_repo,
            [_make_zap_finding()],
            factory,
        )

        findings = triage_repo.fetch_active_findings_for_batching(
            run_id, "zap", "myrepo", "web"
        )

        assert len(findings) == 1

    def test_burp_findings_returned(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = _seed_findings(
            run_repo,
            finding_repo,
            [_make_burp_finding()],
            factory,
        )

        findings = triage_repo.fetch_active_findings_for_batching(
            run_id, "burp", "myrepo", "web"
        )

        assert len(findings) == 1

    def test_zap_finding_contains_renderer_fields(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = _seed_findings(
            run_repo,
            finding_repo,
            [_make_zap_finding()],
            factory,
        )

        findings = triage_repo.fetch_active_findings_for_batching(
            run_id, "zap", "myrepo", "web"
        )
        f = findings[0]

        assert f["id"] is not None
        assert f["repo"] == "myrepo"
        assert f["tool"] == "zap"
        assert f["url"] == "https://example.com/login"
        assert f["alert_name"] == "SQL Injection"
        assert f["method"] == "POST"
        assert f["evidence"] == "SQL syntax error"
        assert f["risk_type"] == "SQL Injection"
        assert f["param"] == "id"
        assert f["attack"] == "' OR '1'='1"

    def test_burp_finding_contains_renderer_fields(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = _seed_findings(
            run_repo,
            finding_repo,
            [_make_burp_finding()],
            factory,
        )

        findings = triage_repo.fetch_active_findings_for_batching(
            run_id, "burp", "myrepo", "web"
        )
        f = findings[0]

        assert f["id"] is not None
        assert f["repo"] == "myrepo"
        assert f["tool"] == "burp"
        assert f["url"] == "https://example.com/search"
        assert f["alert_name"] == "Reflected XSS"
        assert f["method"] == "GET"
        assert f["evidence"] is not None
        assert f["remediation"] == "Encode output"
        assert f["fingerprint_type"] == "REFLECTED_XSS"
        assert f["risk_type"] == "Cross-site scripting"

    def test_web_batches_are_size_one(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = _seed_findings(
            run_repo,
            finding_repo,
            [
                _make_zap_finding(url="https://example.com/a"),
                _make_zap_finding(url="https://example.com/b"),
                _make_zap_finding(url="https://example.com/c"),
            ],
            factory,
        )

        findings = triage_repo.fetch_active_findings_for_batching(
            run_id, "zap", "myrepo", "web"
        )
        batches = compute_batches(
            findings,
            max_findings_per_batch=batch_size_for_segment("web"),
        )

        assert len(batches) == 3
        assert all(len(b) == 1 for b in batches)

    def test_sast_batching_unchanged(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        sast_findings = [
            {
                "tool": "semgrep",
                "repo": "myrepo",
                "segment": "sast",
                "file_path": "src/foo.py",
                "rule_id": "r1",
                "severity": "medium",
                "risk_type": "injection",
                "line_start": 10,
            },
            {
                "tool": "semgrep",
                "repo": "myrepo",
                "segment": "sast",
                "file_path": "src/foo.py",
                "rule_id": "r2",
                "severity": "medium",
                "risk_type": "injection",
                "line_start": 20,
            },
        ]
        run_id = _seed_findings(
            run_repo,
            finding_repo,
            sast_findings,
            factory,
        )

        findings = triage_repo.fetch_active_findings_for_batching(
            run_id, "semgrep", "myrepo", "sast"
        )

        assert len(findings) == 2
        assert findings[0]["file"] == "src/foo.py"
        assert findings[0]["line_start"] is not None
