"""Unit tests for application.reporting.draft_query.DraftQueryService."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.draft_query import DraftQueryService  # noqa: E402
from domain.findings.entry import Finding  # noqa: E402


def _make_finding(**kwargs: Any) -> Finding:
    defaults: dict[str, Any] = {
        "id": 0,
        "fingerprint": None,
        "run_id": None,
        "tool": None,
        "domain": None,
        "segment": None,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


class TestDraftQueryService(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = MagicMock()
        self.svc = DraftQueryService(self.repo)

    # get_filtered_findings

    def test_get_filtered_findings_default(self) -> None:
        sentinel = [_make_finding(id=1)]
        self.repo.get_reportable_findings.return_value = sentinel
        result = self.svc.get_filtered_findings()
        self.repo.get_reportable_findings.assert_called_once()
        self.repo.get_all_findings.assert_not_called()
        self.assertEqual(result, sentinel)

    def test_get_filtered_findings_skip_triage(self) -> None:
        sentinel = [_make_finding(id=2)]
        self.repo.get_all_findings.return_value = sentinel
        result = self.svc.get_filtered_findings(skip_triage=True)
        self.repo.get_all_findings.assert_called_once()
        self.repo.get_reportable_findings.assert_not_called()
        self.assertEqual(result, sentinel)

    # get_findings_for_report

    def test_get_findings_for_report_default_uses_reportable_query(self) -> None:
        sentinel = [_make_finding(id=1)]
        self.repo.get_reportable_findings.return_value = sentinel
        result = self.svc.get_findings_for_report()
        self.repo.get_reportable_findings.assert_called_once()
        self.repo.get_findings_marked_for_report.assert_not_called()
        self.assertEqual(result, sentinel)

    def test_get_findings_for_report_skip_triage_uses_marked_query(self) -> None:
        sentinel = [_make_finding(id=2)]
        self.repo.get_findings_marked_for_report.return_value = sentinel
        result = self.svc.get_findings_for_report(skip_triage=True)
        self.repo.get_findings_marked_for_report.assert_called_once()
        self.repo.get_reportable_findings.assert_not_called()
        self.assertEqual(result, sentinel)

    # severity_distribution

    def test_severity_distribution_mixed(self) -> None:
        findings = [
            _make_finding(severity="critical"),
            _make_finding(severity="High"),
            _make_finding(severity="medium"),
            _make_finding(severity="LOW"),
            _make_finding(severity="informational"),
            _make_finding(severity="unknown"),
            _make_finding(severity=None),
        ]
        dist = self.svc.severity_distribution(findings)
        self.assertEqual(dist["critical"], 1)
        self.assertEqual(dist["high"], 1)
        self.assertEqual(dist["medium"], 1)
        self.assertEqual(dist["low"], 1)
        self.assertEqual(dist["informational"], 1)
        self.assertEqual(sum(dist.values()), 5)

    def test_severity_distribution_empty(self) -> None:
        dist = self.svc.severity_distribution([])
        self.assertEqual(
            dist,
            {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "informational": 0,
            },
        )

    # confidence_distribution

    def test_confidence_distribution_mixed(self) -> None:
        findings = [
            _make_finding(confidence="confirmed"),
            _make_finding(confidence="Probable"),
            _make_finding(confidence="potential"),
            _make_finding(confidence="unknown"),
        ]
        dist = self.svc.confidence_distribution(findings)
        self.assertEqual(dist["confirmed"], 1)
        self.assertEqual(dist["probable"], 1)
        self.assertEqual(dist["potential"], 1)
        self.assertEqual(sum(dist.values()), 3)

    def test_confidence_distribution_empty(self) -> None:
        dist = self.svc.confidence_distribution([])
        self.assertEqual(dist, {"confirmed": 0, "probable": 0, "potential": 0})

    # build_risk_counts

    def test_build_risk_counts_populated(self) -> None:
        findings = [
            _make_finding(severity="critical", confidence="confirmed", seen_count=1),
            _make_finding(severity="high", confidence="confirmed", seen_count=1),
            _make_finding(severity="high", confidence="confirmed", seen_count=1),
            _make_finding(severity="medium", confidence="probable", seen_count=1),
            _make_finding(severity="medium", confidence="confirmed", seen_count=1),
            _make_finding(severity="low", confidence="confirmed", seen_count=1),
            _make_finding(severity="low", confidence="probable", seen_count=1),
            _make_finding(severity="low", confidence="potential", seen_count=1),
            _make_finding(severity="high", confidence="probable", seen_count=2),
        ]
        rc = self.svc.build_risk_counts(findings)
        self.assertEqual(rc.confirmed_critical, 1)
        self.assertEqual(rc.confirmed_high, 2)
        self.assertEqual(rc.prob_confirmed_medium, 2)
        self.assertEqual(rc.low_total, 3)
        self.assertEqual(rc.recurring, 1)

    def test_build_risk_counts_empty(self) -> None:
        rc = self.svc.build_risk_counts([])
        self.assertEqual(rc.confirmed_critical, 0)
        self.assertEqual(rc.confirmed_high, 0)
        self.assertEqual(rc.prob_confirmed_medium, 0)
        self.assertEqual(rc.low_total, 0)
        self.assertEqual(rc.recurring, 0)

    # top_findings

    def test_top_findings_sorted(self) -> None:
        findings = [
            _make_finding(id=1, severity="low", confidence="confirmed"),
            _make_finding(id=2, severity="critical", confidence="confirmed"),
            _make_finding(id=3, severity="high", confidence="probable"),
            _make_finding(id=4, severity="medium", confidence="confirmed"),
            _make_finding(id=5, severity="critical", confidence="probable"),
            _make_finding(id=6, severity="high", confidence="confirmed"),
        ]
        top = self.svc.top_findings(findings, n=3)
        self.assertEqual(len(top), 3)
        self.assertEqual(top[0].id, 2)
        self.assertEqual(top[1].id, 5)
        self.assertEqual(top[2].id, 6)

    def test_top_findings_fewer_than_n(self) -> None:
        findings = [
            _make_finding(id=1, severity="high", confidence="confirmed"),
            _make_finding(id=2, severity="low", confidence="probable"),
        ]
        top = self.svc.top_findings(findings, n=5)
        self.assertEqual(len(top), 2)

    def test_top_findings_unknown_severity_sorts_last(self) -> None:
        findings = [
            _make_finding(id=1, severity="unknown", confidence="confirmed"),
            _make_finding(id=2, severity="critical", confidence="confirmed"),
        ]
        top = self.svc.top_findings(findings, n=2)
        self.assertEqual(top[0].id, 2)
        self.assertEqual(top[1].id, 1)

    # risk_type_groups

    def test_risk_type_groups_normal(self) -> None:
        findings = [
            _make_finding(meta={"risk_type": "SQL Injection"}),
            _make_finding(meta={"risk_type": "SQL Injection"}),
            _make_finding(meta={"risk_type": "XSS"}),
            _make_finding(meta={"risk_type": "Path Traversal"}),
        ]
        groups = self.svc.risk_type_groups(findings, top_n=2)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], ("SQL Injection", 2))
        self.assertEqual(groups[1][1], 1)

    def test_risk_type_groups_no_risk_type(self) -> None:
        findings = [
            _make_finding(meta={"other_key": "value"}),
            _make_finding(meta={}),
        ]
        groups = self.svc.risk_type_groups(findings)
        self.assertEqual(groups, [])

    # distinct_tools

    def test_distinct_tools_deduped_sorted(self) -> None:
        findings = [
            _make_finding(tool="semgrep"),
            _make_finding(tool="gitleaks"),
            _make_finding(tool="semgrep"),
        ]
        result = self.svc.distinct_tools(findings)
        self.assertEqual(result, ["gitleaks", "semgrep"])

    def test_distinct_tools_empty(self) -> None:
        self.assertEqual(self.svc.distinct_tools([]), [])

    # distinct_repos

    def test_distinct_repos_deduped_sorted(self) -> None:
        findings = [
            _make_finding(meta={"repo": "repo-b"}),
            _make_finding(meta={"repo": "repo-a"}),
            _make_finding(meta={"repo": "repo-b"}),
        ]
        result = self.svc.distinct_repos(findings)
        self.assertEqual(result, ["repo-a", "repo-b"])

    # distinct_url_hosts

    def test_distinct_url_hosts_zap(self) -> None:
        findings = [
            _make_finding(tool="zap", url="https://example.com:8443/path"),
            _make_finding(tool="zap", url="http://other.local/"),
        ]
        result = self.svc.distinct_url_hosts(findings)
        self.assertEqual(result, ["example.com:8443", "other.local"])

    def test_distinct_url_hosts_non_zap_excluded(self) -> None:
        findings = [
            _make_finding(tool="semgrep", url="https://example.com/vuln"),
        ]
        result = self.svc.distinct_url_hosts(findings)
        self.assertEqual(result, [])

    def test_distinct_url_hosts_empty_url_skipped(self) -> None:
        findings = [
            _make_finding(tool="zap", url=""),
        ]
        result = self.svc.distinct_url_hosts(findings)
        self.assertEqual(result, [])

    # distinct_ecosystems

    def test_distinct_ecosystems_sca(self) -> None:
        findings = [
            _make_finding(tool="pip-audit", ecosystem="PyPI"),
            _make_finding(tool="npm-audit", ecosystem="npm"),
        ]
        result = self.svc.distinct_ecosystems(findings)
        self.assertEqual(result, ["PyPI", "npm"])

    def test_distinct_ecosystems_non_sca_excluded(self) -> None:
        findings = [
            _make_finding(tool="semgrep", ecosystem="PyPI"),
        ]
        result = self.svc.distinct_ecosystems(findings)
        self.assertEqual(result, [])

    # recurring_findings

    def test_recurring_findings_filters(self) -> None:
        findings = [
            _make_finding(id=1, seen_count=0),
            _make_finding(id=2, seen_count=1),
            _make_finding(id=3, seen_count=2),
            _make_finding(id=4, seen_count=3),
        ]
        result = self.svc.recurring_findings(findings)
        ids = [f.id for f in result]
        self.assertEqual(ids, [3, 4])

    def test_recurring_findings_missing_seen_count(self) -> None:
        findings = [
            _make_finding(id=1),
            _make_finding(id=2, seen_count=None),
        ]
        result = self.svc.recurring_findings(findings)
        self.assertEqual(result, [])

    # recurring_by_risk_type

    def test_recurring_by_risk_type_groups(self) -> None:
        findings = [
            _make_finding(id=1, seen_count=2, meta={"risk_type": "SQL Injection"}),
            _make_finding(id=2, seen_count=3, meta={"risk_type": "SQL Injection"}),
            _make_finding(id=3, seen_count=2, meta={"risk_type": "XSS"}),
            _make_finding(id=4, seen_count=1, meta={"risk_type": "SQL Injection"}),
        ]
        groups = self.svc.recurring_by_risk_type(findings)
        self.assertIn("SQL Injection", groups)
        self.assertIn("XSS", groups)
        self.assertEqual(len(groups["SQL Injection"]), 2)
        self.assertEqual(len(groups["XSS"]), 1)

    def test_recurring_by_risk_type_no_risk_type(self) -> None:
        findings = [_make_finding(id=1, seen_count=2, meta={})]
        groups = self.svc.recurring_by_risk_type(findings)
        self.assertIn("unclassified", groups)
        self.assertEqual(len(groups["unclassified"]), 1)
