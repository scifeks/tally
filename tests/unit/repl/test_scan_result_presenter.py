"""Unit tests for ScanResultPresenter."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest

from application.repl.commands.scan_result_presenter import ScanResultPresenter
from domain.tools.base import ToolResult


def _make_result(
    tool_name: str,
    success: bool,
    parsed_data: dict | None,
    output: str = "",
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=success,
        output=output,
        parsed_data=parsed_data,
        output_files={},
        timestamp="2026-01-01T00:00:00",
        duration_seconds=1.0,
    )


@pytest.mark.unit
class TestScanResultPresenterDispatch(unittest.TestCase):
    def setUp(self) -> None:
        self.console = MagicMock()
        self.presenter = ScanResultPresenter(self.console)

    def _first_printed(self) -> str:
        return self.console.print.call_args_list[-1][0][0]

    def test_present_gitleaks_dispatches_to_gitleaks_handler(self) -> None:
        result = _make_result(
            "gitleaks",
            True,
            {"summary": {"total_secrets": 0}},
        )
        self.presenter.present(result)
        self.assertTrue(self.console.print.called)
        printed = self._first_printed()
        self.assertIn("Scan complete", printed)

    def test_present_semgrep_dispatches_to_semgrep_handler(self) -> None:
        result = _make_result(
            "semgrep",
            True,
            {"summary": {"total_findings": 0, "by_severity": {}}},
        )
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_osv_scanner_dispatches_to_sca_handler(self) -> None:
        result = _make_result(
            "osv-scanner",
            True,
            {"summary": {"total_vulnerabilities": 0, "by_severity": {}}},
        )
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_pip_audit_dispatches_to_sca_handler(self) -> None:
        result = _make_result(
            "pip-audit",
            True,
            {"summary": {"total_vulnerabilities": 0, "by_severity": {}}},
        )
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_npm_audit_dispatches_to_sca_handler(self) -> None:
        result = _make_result(
            "npm-audit",
            True,
            {"summary": {"total_vulnerabilities": 0, "by_severity": {}}},
        )
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_composer_audit_dispatches_to_sca_handler(self) -> None:
        result = _make_result(
            "composer-audit",
            True,
            {"summary": {"total_vulnerabilities": 0, "by_severity": {}}},
        )
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_zap_dispatches_to_zap_handler(self) -> None:
        result = _make_result(
            "zap",
            True,
            {
                "summary": {
                    "total_alerts": 0,
                    "by_risk": {},
                    "urls_scanned": 0,
                }
            },
        )
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_nmap_dispatches_to_generic_handler(self) -> None:
        result = _make_result("nmap", True, None)
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())

    def test_present_custom_tool_dispatches_to_generic_handler(self) -> None:
        result = _make_result("my-custom-tool", True, None)
        self.presenter.present(result)
        self.assertIn("Scan complete", self._first_printed())


@pytest.mark.unit
class TestScanResultPresenterGitleaks(unittest.TestCase):
    def setUp(self) -> None:
        self.console = MagicMock()
        self.presenter = ScanResultPresenter(self.console)

    def test_gitleaks_success_with_secrets_prints_warning_and_scan_complete(
        self,
    ) -> None:
        result = _make_result(
            "gitleaks",
            True,
            {
                "summary": {
                    "total_secrets": 3,
                    "files_with_secrets": 2,
                    "by_rule": {"api-key": 2, "password": 1},
                }
            },
        )
        self.presenter.present(result)
        calls = self.console.print.call_args_list
        self.assertTrue(
            any("WARNING" in str(c) for c in calls),
            "Expected WARNING in one of the print calls",
        )
        self.assertTrue(
            any("Scan complete" in str(c) for c in calls),
            "Expected 'Scan complete' in one of the print calls",
        )

    def test_gitleaks_success_clean_prints_scan_complete_and_clean_summary(
        self,
    ) -> None:
        result = _make_result(
            "gitleaks",
            True,
            {"summary": {"total_secrets": 0}},
        )
        self.presenter.present(result)
        calls = self.console.print.call_args_list
        all_output = " ".join(str(c) for c in calls)
        self.assertIn("Scan complete", all_output)
        self.assertIn("0 secrets found (clean)", all_output)

    def test_gitleaks_failure_prints_scan_failed(self) -> None:
        result = _make_result(
            "gitleaks",
            False,
            None,
            output="error msg",
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan failed", printed)

    def test_gitleaks_parsed_data_with_error_key_and_success_false_prints_failed(
        self,
    ) -> None:
        result = _make_result(
            "gitleaks",
            False,
            {"error": "something went wrong"},
            output="error msg",
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan failed", printed)

    def test_gitleaks_parsed_data_with_error_key_and_success_true_prints_complete(
        self,
    ) -> None:
        result = _make_result(
            "gitleaks",
            True,
            {"error": "something went wrong"},
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan complete", printed)

    def test_gitleaks_no_parsed_data_and_success_true_prints_scan_complete(
        self,
    ) -> None:
        result = _make_result("gitleaks", True, None)
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("scan complete", printed)


@pytest.mark.unit
class TestScanResultPresenterSemgrep(unittest.TestCase):
    def setUp(self) -> None:
        self.console = MagicMock()
        self.presenter = ScanResultPresenter(self.console)

    def test_semgrep_success_with_findings_prints_finding_count(self) -> None:
        result = _make_result(
            "semgrep",
            True,
            {
                "summary": {
                    "total_findings": 5,
                    "by_severity": {"high": 2, "medium": 3},
                }
            },
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("5 findings", printed)

    def test_semgrep_no_parsed_data_success_true_prints_scan_complete(self) -> None:
        result = _make_result("semgrep", True, None)
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("scan complete", printed)

    def test_semgrep_failure_prints_scan_failed(self) -> None:
        result = _make_result(
            "semgrep",
            False,
            None,
            output="semgrep error",
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan failed", printed)


@pytest.mark.unit
class TestScanResultPresenterSca(unittest.TestCase):
    def setUp(self) -> None:
        self.console = MagicMock()
        self.presenter = ScanResultPresenter(self.console)

    def test_sca_success_with_vulns_prints_vulnerability_count(self) -> None:
        result = _make_result(
            "pip-audit",
            True,
            {
                "summary": {
                    "total_vulnerabilities": 10,
                    "by_severity": {
                        "critical": 1,
                        "high": 3,
                        "medium": 4,
                        "low": 2,
                    },
                }
            },
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("10 vulnerabilities", printed)

    def test_sca_no_parsed_data_success_true_prints_scan_complete(self) -> None:
        result = _make_result("pip-audit", True, None)
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("scan complete", printed)

    def test_sca_failure_prints_scan_failed(self) -> None:
        result = _make_result(
            "pip-audit",
            False,
            None,
            output="pip-audit error",
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan failed", printed)


@pytest.mark.unit
class TestScanResultPresenterZap(unittest.TestCase):
    def setUp(self) -> None:
        self.console = MagicMock()
        self.presenter = ScanResultPresenter(self.console)

    def test_zap_success_with_alerts_prints_alert_count_and_url_count(
        self,
    ) -> None:
        result = _make_result(
            "zap",
            True,
            {
                "summary": {
                    "total_alerts": 8,
                    "by_risk": {"high": 1, "medium": 3, "low": 4},
                    "urls_scanned": 25,
                }
            },
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("8 alerts", printed)
        self.assertIn("25 URLs scanned", printed)

    def test_zap_failure_with_long_output_prints_scan_failed_truncated(
        self,
    ) -> None:
        long_output = "x" * 300
        result = _make_result("zap", False, None, output=long_output)
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan failed", printed)
        # The output portion embedded in the printed string must be truncated.
        # The format is "[red]✗ Scan failed:[/red] <output[:200]>"
        # Extract the portion after the closing markup tag.
        suffix = printed.split("[/red] ", 1)[1] if "[/red] " in printed else printed
        self.assertLessEqual(len(suffix), 200)


@pytest.mark.unit
class TestScanResultPresenterGeneric(unittest.TestCase):
    def setUp(self) -> None:
        self.console = MagicMock()
        self.presenter = ScanResultPresenter(self.console)

    def test_generic_success_with_hosts_prints_host_and_port_counts(self) -> None:
        result = _make_result(
            "nmap",
            True,
            {
                "hosts": [
                    {
                        "state": "up",
                        "ports": [
                            {"state": "open"},
                            {"state": "closed"},
                        ],
                    },
                    {"state": "down", "ports": []},
                ]
            },
        )
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("1 hosts up, 1 open ports", printed)

    def test_generic_no_parsed_data_success_true_prints_scan_complete(self) -> None:
        result = _make_result("nmap", True, None)
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("scan complete", printed)

    def test_generic_failure_prints_scan_failed(self) -> None:
        result = _make_result("nmap", False, None, output="nmap error")
        self.presenter.present(result)
        printed = self.console.print.call_args[0][0]
        self.assertIn("Scan failed", printed)


@pytest.mark.unit
class TestScanResultPresenterStaticSummaries(unittest.TestCase):
    def test_summarize_gitleaks_with_secrets(self) -> None:
        result = _make_result(
            "gitleaks",
            True,
            {
                "summary": {
                    "total_secrets": 3,
                    "files_with_secrets": 2,
                    "by_rule": {"api-key": 2, "password": 1},
                }
            },
        )
        summary = ScanResultPresenter._summarize_gitleaks(result)
        self.assertEqual(
            summary,
            "3 secrets in 2 file(s) (2 api-key, 1 password)",
        )

    def test_summarize_semgrep_with_findings(self) -> None:
        result = _make_result(
            "semgrep",
            True,
            {
                "summary": {
                    "total_findings": 5,
                    "by_severity": {"high": 2, "medium": 3},
                }
            },
        )
        summary = ScanResultPresenter._summarize_semgrep(result)
        self.assertEqual(summary, "5 findings (2 high, 3 medium)")

    def test_summarize_sca_with_vulnerabilities(self) -> None:
        result = _make_result(
            "pip-audit",
            True,
            {
                "summary": {
                    "total_vulnerabilities": 10,
                    "by_severity": {
                        "critical": 1,
                        "high": 3,
                        "medium": 4,
                        "low": 2,
                    },
                }
            },
        )
        summary = ScanResultPresenter._summarize_sca(result)
        self.assertEqual(
            summary,
            "10 vulnerabilities (1 critical, 3 high, 4 medium, 2 low)",
        )

    def test_summarize_zap_with_alerts(self) -> None:
        result = _make_result(
            "zap",
            True,
            {
                "summary": {
                    "total_alerts": 8,
                    "by_risk": {"high": 1, "medium": 3, "low": 4},
                    "urls_scanned": 25,
                }
            },
        )
        summary = ScanResultPresenter._summarize_zap(result)
        self.assertEqual(
            summary,
            "8 alerts (1 high, 3 medium, 4 low), 25 URLs scanned",
        )

    def test_summarize_generic_with_hosts(self) -> None:
        result = _make_result(
            "nmap",
            True,
            {
                "hosts": [
                    {
                        "state": "up",
                        "ports": [
                            {"state": "open"},
                            {"state": "closed"},
                        ],
                    },
                    {"state": "down", "ports": []},
                ]
            },
        )
        summary = ScanResultPresenter._summarize_generic(result)
        self.assertEqual(summary, "1 hosts up, 1 open ports")
