"""Unit tests for application.reporting.draft_query.DraftQueryService."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.draft_query import (  # noqa: E402
    DraftQueryService,
    _parse_meta,
)


@pytest.mark.unit
class TestDraftQueryService(unittest.TestCase):
    """Tests for DraftQueryService and module-level _parse_meta."""

    def setUp(self) -> None:
        self.repo = MagicMock()
        self.svc = DraftQueryService(self.repo)

    # ------------------------------------------------------------------ #
    # get_filtered_findings
    # ------------------------------------------------------------------ #

    def test_get_filtered_findings_default(self) -> None:
        self.repo.get_reportable_findings.return_value = [{"id": 1}]
        result = self.svc.get_filtered_findings()
        self.repo.get_reportable_findings.assert_called_once()
        self.repo.get_all_findings.assert_not_called()
        self.assertEqual(result, [{"id": 1}])

    def test_get_filtered_findings_skip_triage(self) -> None:
        self.repo.get_all_findings.return_value = [{"id": 2}]
        result = self.svc.get_filtered_findings(skip_triage=True)
        self.repo.get_all_findings.assert_called_once()
        self.repo.get_reportable_findings.assert_not_called()
        self.assertEqual(result, [{"id": 2}])

    # ------------------------------------------------------------------ #
    # severity_distribution
    # ------------------------------------------------------------------ #

    def test_severity_distribution_mixed(self) -> None:
        findings = [
            {"severity": "critical"},
            {"severity": "High"},
            {"severity": "medium"},
            {"severity": "LOW"},
            {"severity": "informational"},
            {"severity": "unknown"},
            {"severity": None},
        ]
        dist = self.svc.severity_distribution(findings)
        self.assertEqual(dist["critical"], 1)
        self.assertEqual(dist["high"], 1)
        self.assertEqual(dist["medium"], 1)
        self.assertEqual(dist["low"], 1)
        self.assertEqual(dist["informational"], 1)
        # "unknown" and None are not counted
        total = sum(dist.values())
        self.assertEqual(total, 5)

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

    # ------------------------------------------------------------------ #
    # confidence_distribution
    # ------------------------------------------------------------------ #

    def test_confidence_distribution_mixed(self) -> None:
        findings = [
            {"confidence": "confirmed"},
            {"confidence": "Probable"},
            {"confidence": "potential"},
            {"confidence": "unknown"},
        ]
        dist = self.svc.confidence_distribution(findings)
        self.assertEqual(dist["confirmed"], 1)
        self.assertEqual(dist["probable"], 1)
        self.assertEqual(dist["potential"], 1)
        self.assertEqual(sum(dist.values()), 3)

    def test_confidence_distribution_empty(self) -> None:
        dist = self.svc.confidence_distribution([])
        self.assertEqual(dist, {"confirmed": 0, "probable": 0, "potential": 0})

    # ------------------------------------------------------------------ #
    # build_risk_counts
    # ------------------------------------------------------------------ #

    def test_build_risk_counts_populated(self) -> None:
        findings = [
            # confirmed-critical
            {"severity": "critical", "confidence": "confirmed", "seen_count": 1},
            # confirmed-high (x2)
            {"severity": "high", "confidence": "confirmed", "seen_count": 1},
            {"severity": "high", "confidence": "confirmed", "seen_count": 1},
            # probable-medium
            {"severity": "medium", "confidence": "probable", "seen_count": 1},
            # confirmed-medium
            {"severity": "medium", "confidence": "confirmed", "seen_count": 1},
            # low (x3)
            {"severity": "low", "confidence": "confirmed", "seen_count": 1},
            {"severity": "low", "confidence": "probable", "seen_count": 1},
            {"severity": "low", "confidence": "potential", "seen_count": 1},
            # recurring
            {"severity": "high", "confidence": "probable", "seen_count": 2},
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

    # ------------------------------------------------------------------ #
    # top_findings
    # ------------------------------------------------------------------ #

    def test_top_findings_sorted(self) -> None:
        findings = [
            {"id": 1, "severity": "low", "confidence": "confirmed"},
            {"id": 2, "severity": "critical", "confidence": "confirmed"},
            {"id": 3, "severity": "high", "confidence": "probable"},
            {"id": 4, "severity": "medium", "confidence": "confirmed"},
            {"id": 5, "severity": "critical", "confidence": "probable"},
            {"id": 6, "severity": "high", "confidence": "confirmed"},
        ]
        top = self.svc.top_findings(findings, n=3)
        self.assertEqual(len(top), 3)
        # Best: critical/confirmed, critical/probable, high/confirmed
        self.assertEqual(top[0]["id"], 2)
        self.assertEqual(top[1]["id"], 5)
        self.assertEqual(top[2]["id"], 6)

    def test_top_findings_fewer_than_n(self) -> None:
        findings = [
            {"id": 1, "severity": "high", "confidence": "confirmed"},
            {"id": 2, "severity": "low", "confidence": "probable"},
        ]
        top = self.svc.top_findings(findings, n=5)
        self.assertEqual(len(top), 2)

    def test_top_findings_unknown_severity_sorts_last(self) -> None:
        findings = [
            {"id": 1, "severity": "unknown", "confidence": "confirmed"},
            {"id": 2, "severity": "critical", "confidence": "confirmed"},
        ]
        top = self.svc.top_findings(findings, n=2)
        self.assertEqual(top[0]["id"], 2)
        self.assertEqual(top[1]["id"], 1)

    # ------------------------------------------------------------------ #
    # risk_type_groups
    # ------------------------------------------------------------------ #

    def test_risk_type_groups_normal(self) -> None:
        findings = [
            {"meta": {"risk_type": "SQL Injection"}},
            {"meta": {"risk_type": "SQL Injection"}},
            {"meta": {"risk_type": "XSS"}},
            {"meta": {"risk_type": "Path Traversal"}},
        ]
        groups = self.svc.risk_type_groups(findings, top_n=2)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], ("SQL Injection", 2))
        self.assertEqual(groups[1][1], 1)

    def test_risk_type_groups_no_risk_type(self) -> None:
        findings = [
            {"meta": {"other_key": "value"}},
            {"meta": {}},
        ]
        groups = self.svc.risk_type_groups(findings)
        self.assertEqual(groups, [])

    def test_risk_type_groups_meta_as_json_string(self) -> None:
        findings = [
            {"meta": '{"risk_type": "SSRF"}'},
            {"meta": '{"risk_type": "SSRF"}'},
        ]
        groups = self.svc.risk_type_groups(findings)
        self.assertEqual(groups, [("SSRF", 2)])

    # ------------------------------------------------------------------ #
    # distinct_tools
    # ------------------------------------------------------------------ #

    def test_distinct_tools_deduped_sorted(self) -> None:
        findings = [
            {"tool": "semgrep"},
            {"tool": "gitleaks"},
            {"tool": "semgrep"},
        ]
        result = self.svc.distinct_tools(findings)
        self.assertEqual(result, ["gitleaks", "semgrep"])

    def test_distinct_tools_empty(self) -> None:
        self.assertEqual(self.svc.distinct_tools([]), [])

    # ------------------------------------------------------------------ #
    # distinct_repos
    # ------------------------------------------------------------------ #

    def test_distinct_repos_deduped_sorted(self) -> None:
        findings = [
            {"repo": "repo-b"},
            {"repo": "repo-a"},
            {"repo": "repo-b"},
        ]
        result = self.svc.distinct_repos(findings)
        self.assertEqual(result, ["repo-a", "repo-b"])

    # ------------------------------------------------------------------ #
    # distinct_url_hosts
    # ------------------------------------------------------------------ #

    def test_distinct_url_hosts_zap(self) -> None:
        findings = [
            {"tool": "zap", "url": "https://example.com:8443/path"},
            {"tool": "zap", "url": "http://other.local/"},
        ]
        result = self.svc.distinct_url_hosts(findings)
        self.assertEqual(result, ["example.com:8443", "other.local"])

    def test_distinct_url_hosts_non_zap_excluded(self) -> None:
        findings = [
            {"tool": "semgrep", "url": "https://example.com/vuln"},
        ]
        result = self.svc.distinct_url_hosts(findings)
        self.assertEqual(result, [])

    def test_distinct_url_hosts_empty_url_skipped(self) -> None:
        findings = [
            {"tool": "zap", "url": ""},
        ]
        result = self.svc.distinct_url_hosts(findings)
        self.assertEqual(result, [])

    # ------------------------------------------------------------------ #
    # distinct_hosts
    # ------------------------------------------------------------------ #

    def test_distinct_hosts_nmap(self) -> None:
        findings = [
            {"tool": "nmap", "host": "10.0.0.1"},
            {"tool": "nmap", "host": "10.0.0.2"},
            {"tool": "nmap", "host": "10.0.0.1"},
        ]
        result = self.svc.distinct_hosts(findings)
        self.assertEqual(result, ["10.0.0.1", "10.0.0.2"])

    def test_distinct_hosts_non_nmap_excluded(self) -> None:
        findings = [
            {"tool": "semgrep", "host": "10.0.0.1"},
        ]
        result = self.svc.distinct_hosts(findings)
        self.assertEqual(result, [])

    # ------------------------------------------------------------------ #
    # distinct_ecosystems
    # ------------------------------------------------------------------ #

    def test_distinct_ecosystems_sca(self) -> None:
        findings = [
            {"tool": "pip-audit", "ecosystem": "PyPI"},
            {"tool": "npm-audit", "ecosystem": "npm"},
        ]
        result = self.svc.distinct_ecosystems(findings)
        self.assertEqual(result, ["PyPI", "npm"])

    def test_distinct_ecosystems_non_sca_excluded(self) -> None:
        findings = [
            {"tool": "semgrep", "ecosystem": "PyPI"},
        ]
        result = self.svc.distinct_ecosystems(findings)
        self.assertEqual(result, [])

    # ------------------------------------------------------------------ #
    # recurring_findings
    # ------------------------------------------------------------------ #

    def test_recurring_findings_filters(self) -> None:
        findings = [
            {"id": 1, "seen_count": 0},
            {"id": 2, "seen_count": 1},
            {"id": 3, "seen_count": 2},
            {"id": 4, "seen_count": 3},
        ]
        result = self.svc.recurring_findings(findings)
        ids = [f["id"] for f in result]
        self.assertEqual(ids, [3, 4])

    def test_recurring_findings_missing_seen_count(self) -> None:
        findings = [
            {"id": 1},
            {"id": 2, "seen_count": None},
        ]
        result = self.svc.recurring_findings(findings)
        self.assertEqual(result, [])

    # ------------------------------------------------------------------ #
    # recurring_by_risk_type
    # ------------------------------------------------------------------ #

    def test_recurring_by_risk_type_groups(self) -> None:
        findings = [
            {
                "id": 1,
                "seen_count": 2,
                "meta": {"risk_type": "SQL Injection"},
            },
            {
                "id": 2,
                "seen_count": 3,
                "meta": {"risk_type": "SQL Injection"},
            },
            {
                "id": 3,
                "seen_count": 2,
                "meta": {"risk_type": "XSS"},
            },
            # Not recurring — should be excluded
            {
                "id": 4,
                "seen_count": 1,
                "meta": {"risk_type": "SQL Injection"},
            },
        ]
        groups = self.svc.recurring_by_risk_type(findings)
        self.assertIn("SQL Injection", groups)
        self.assertIn("XSS", groups)
        self.assertEqual(len(groups["SQL Injection"]), 2)
        self.assertEqual(len(groups["XSS"]), 1)

    def test_recurring_by_risk_type_no_risk_type(self) -> None:
        findings = [
            {"id": 1, "seen_count": 2, "meta": {}},
        ]
        groups = self.svc.recurring_by_risk_type(findings)
        self.assertIn("unclassified", groups)
        self.assertEqual(len(groups["unclassified"]), 1)

    # ------------------------------------------------------------------ #
    # _parse_meta (module-level function)
    # ------------------------------------------------------------------ #

    def test_parse_meta_json_string(self) -> None:
        finding = {"meta": '{"risk_type": "XSS", "cwe": 79}'}
        result = _parse_meta(finding)
        self.assertEqual(result, {"risk_type": "XSS", "cwe": 79})

    def test_parse_meta_dict(self) -> None:
        meta = {"risk_type": "SSRF", "cvss": 7.5}
        finding = {"meta": meta}
        result = _parse_meta(finding)
        self.assertIs(result, meta)

    def test_parse_meta_invalid_json(self) -> None:
        finding = {"meta": "not-valid-json{{{"}
        result = _parse_meta(finding)
        self.assertEqual(result, {})

    def test_parse_meta_none(self) -> None:
        finding = {"meta": None}
        result = _parse_meta(finding)
        self.assertEqual(result, {})

    def test_parse_meta_missing_key(self) -> None:
        finding: dict = {}
        result = _parse_meta(finding)
        self.assertEqual(result, {})
