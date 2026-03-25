"""Unit tests for application.reporting.findings_builder."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.findings_builder import FindingsBuilder  # noqa: E402

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _finding(**kwargs: Any) -> dict[str, Any]:
    """Return a minimal code finding dict with optional overrides."""
    base: dict[str, Any] = {
        "id": 1,
        "tal_id": "TAL-001",
        "tool": "semgrep",
        "severity": "high",
        "confidence": "confirmed",
        "status": "active",
        "seen_count": 1,
        "repo": "backend",
        "file": "app/auth.py",
        "rule_id": "sqli",
        "description": "SQL injection",
        "meta": "{}",
        "package_name": None,
        "package_version": None,
        "ecosystem": None,
        "domain": "code",
        "segment": "sast",
        "url": None,
        "cwe": None,
        "host": None,
        "port": None,
    }
    base.update(kwargs)
    return base


def _nmap_finding(**kwargs: Any) -> dict[str, Any]:
    """Return a minimal nmap finding dict with optional overrides."""
    base: dict[str, Any] = {
        "id": 100,
        "tool": "nmap",
        "segment": "network",
        "domain": "network",
        "host": "10.0.0.1",
        "port": "80",
        "meta": '{"service": "http", "service_version": "Apache/2.4"}',
        "severity": "informational",
        "confidence": "confirmed",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# TestBuildMasterTable
# ---------------------------------------------------------------------------


class TestBuildMasterTable:
    def test_empty_code_findings_renders_placeholder(self) -> None:
        html = FindingsBuilder().build_master_table([], [])
        assert "placeholder" in html
        assert "No code findings" in html

    def test_empty_nmap_findings_renders_placeholder(self) -> None:
        html = FindingsBuilder().build_master_table([], [])
        assert "No network findings" in html

    def test_code_finding_tal_id_appears(self) -> None:
        html = FindingsBuilder().build_master_table([_finding()], [])
        assert "TAL-001" in html

    def test_missing_tal_id_renders_dash(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(tal_id=None)], [])
        assert "—" in html

    def test_recurring_row_gets_css_class(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(seen_count=3)], [])
        assert "recurring-row" in html

    def test_non_recurring_row_lacks_css_class(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(seen_count=1)], [])
        assert "recurring-row" not in html

    def test_severity_badge_present(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(severity="high")], [])
        assert "severity-badge" in html
        assert "high" in html

    def test_nmap_hosts_grouped(self) -> None:
        findings = [
            _nmap_finding(host="10.0.0.1", port="80"),
            _nmap_finding(host="10.0.0.1", port="443"),
            _nmap_finding(host="10.0.0.2", port="22"),
        ]
        html = FindingsBuilder().build_master_table([], findings)
        # Two distinct hosts → two NW-0xx row IDs.
        assert "NW-001" in html
        assert "NW-002" in html
        assert "10.0.0.1" in html
        assert "10.0.0.2" in html

    def test_nmap_ports_comma_joined(self) -> None:
        findings = [
            _nmap_finding(host="10.0.0.1", port="80"),
            _nmap_finding(host="10.0.0.1", port="443"),
        ]
        html = FindingsBuilder().build_master_table([], findings)
        assert "80, 443" in html or "443, 80" in html

    def test_code_and_network_headings_present(self) -> None:
        html = FindingsBuilder().build_master_table([_finding()], [_nmap_finding()])
        assert "Code Findings" in html
        assert "Network Findings" in html


# ---------------------------------------------------------------------------
# TestBuildCodeCards
# ---------------------------------------------------------------------------


class TestBuildCodeCards:
    def test_empty_returns_placeholder(self) -> None:
        html = FindingsBuilder.build_code_cards([])
        assert "placeholder" in html

    def test_finding_card_class_present(self) -> None:
        html = FindingsBuilder.build_code_cards([_finding()])
        assert "finding-card" in html

    def test_tal_id_in_card(self) -> None:
        html = FindingsBuilder.build_code_cards([_finding(tal_id="TAL-007")])
        assert "TAL-007" in html

    def test_grouped_by_repo(self) -> None:
        findings = [
            _finding(id=1, repo="alpha"),
            _finding(id=2, repo="beta"),
        ]
        html = FindingsBuilder.build_code_cards(findings)
        assert "alpha" in html
        assert "beta" in html
        assert html.index("alpha") < html.index("beta")

    def test_null_repo_goes_to_unattributed(self) -> None:
        html = FindingsBuilder.build_code_cards([_finding(repo=None)])
        assert "Unattributed" in html

    def test_sast_location_shows_file_and_line(self) -> None:
        import json

        meta = json.dumps({"line_start": 42})
        html = FindingsBuilder.build_code_cards(
            [_finding(segment="sast", file="src/foo.py", meta=meta)]
        )
        assert "src/foo.py" in html
        assert "42" in html

    def test_secrets_location_shows_file(self) -> None:
        html = FindingsBuilder.build_code_cards(
            [_finding(segment="secrets", file="config/secrets.env")]
        )
        assert "config/secrets.env" in html

    def test_api_location_shows_method_and_url(self) -> None:
        import json

        meta = json.dumps({"method": "POST"})
        html = FindingsBuilder.build_code_cards(
            [_finding(segment="api", url="https://example.com/login", meta=meta)]
        )
        assert "POST" in html
        assert "https://example.com/login" in html

    def test_sca_location_shows_package_info(self) -> None:
        html = FindingsBuilder.build_code_cards(
            [
                _finding(
                    segment="sca",
                    package_name="requests",
                    package_version="2.28.0",
                    ecosystem="pip",
                )
            ]
        )
        assert "requests" in html
        assert "2.28.0" in html
        assert "pip" in html

    def test_description_present(self) -> None:
        html = FindingsBuilder.build_code_cards(
            [_finding(description="Unsafe deserialization")]
        )
        assert "Unsafe deserialization" in html

    def test_html_escaping_in_title(self) -> None:
        import json

        meta = json.dumps({"title": "<script>xss</script>"})
        html = FindingsBuilder.build_code_cards([_finding(meta=meta)])
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# TestBuildSecretsCards
# ---------------------------------------------------------------------------


class TestBuildSecretsCards:
    def test_empty_returns_placeholder(self) -> None:
        html = FindingsBuilder.build_secrets_cards([])
        assert "placeholder" in html
        assert "No secrets" in html

    def test_repo_name_present(self) -> None:
        html = FindingsBuilder.build_secrets_cards(
            [_finding(segment="secrets", repo="myrepo")]
        )
        assert "myrepo" in html

    def test_null_repo_goes_to_unattributed(self) -> None:
        html = FindingsBuilder.build_secrets_cards(
            [_finding(segment="secrets", repo=None)]
        )
        assert "Unattributed" in html

    def test_total_count_shown(self) -> None:
        findings = [
            _finding(id=1, segment="secrets", repo="r"),
            _finding(id=2, segment="secrets", repo="r"),
        ]
        html = FindingsBuilder.build_secrets_cards(findings)
        assert "2" in html

    def test_rule_id_breakdown_present(self) -> None:
        html = FindingsBuilder.build_secrets_cards(
            [_finding(segment="secrets", rule_id="aws-access-key")]
        )
        assert "aws-access-key" in html

    def test_file_paths_present(self) -> None:
        html = FindingsBuilder.build_secrets_cards(
            [_finding(segment="secrets", file=".env")]
        )
        assert ".env" in html

    def test_no_line_numbers_in_output(self) -> None:
        import json

        meta = json.dumps({"line_number": 99})
        html = FindingsBuilder.build_secrets_cards(
            [_finding(segment="secrets", file=".env", meta=meta)]
        )
        # File path present, but the line number should not appear.
        assert ".env" in html
        assert "99" not in html

    def test_repos_sorted_alphabetically(self) -> None:
        findings = [
            _finding(id=1, segment="secrets", repo="zebra"),
            _finding(id=2, segment="secrets", repo="alpha"),
        ]
        html = FindingsBuilder.build_secrets_cards(findings)
        assert html.index("alpha") < html.index("zebra")


# ---------------------------------------------------------------------------
# TestBuildComprehensiveCodeTable
# ---------------------------------------------------------------------------


class TestBuildComprehensiveCodeTable:
    def test_empty_returns_placeholder(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table([])
        assert "placeholder" in html

    def test_tal_id_in_table(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table([_finding()])
        assert "TAL-001" in html

    def test_owasp_name_from_meta(self) -> None:
        import json

        meta = json.dumps({"owasp_name": "Injection"})
        html = FindingsBuilder().build_comprehensive_code_table([_finding(meta=meta)])
        assert "Injection" in html

    def test_owasp_falls_back_to_cwe(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(cwe='["CWE-89"]')]
        )
        assert "CWE-89" in html

    def test_owasp_falls_back_to_rule_id(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(cwe=None, rule_id="custom-rule")]
        )
        assert "custom-rule" in html

    def test_owasp_falls_back_to_unclassified(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(cwe=None, rule_id=None, meta="{}")]
        )
        assert "Unclassified" in html

    def test_severity_ordering(self) -> None:
        findings = [
            _finding(id=1, tal_id="TAL-001", severity="low", repo="a"),
            _finding(id=2, tal_id="TAL-002", severity="critical", repo="a"),
        ]
        html = FindingsBuilder().build_comprehensive_code_table(findings)
        assert html.index("TAL-002") < html.index("TAL-001")

    def test_null_repo_shows_unattributed(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table([_finding(repo=None)])
        assert "Unattributed" in html


# ---------------------------------------------------------------------------
# TestBuildComprehensiveNetworkTable
# ---------------------------------------------------------------------------


class TestBuildComprehensiveNetworkTable:
    def test_empty_returns_placeholder(self) -> None:
        html = FindingsBuilder.build_comprehensive_network_table([])
        assert "placeholder" in html

    def test_host_present(self) -> None:
        html = FindingsBuilder.build_comprehensive_network_table(
            [_nmap_finding(host="192.168.1.1")]
        )
        assert "192.168.1.1" in html

    def test_nw_tal_id_assigned(self) -> None:
        html = FindingsBuilder.build_comprehensive_network_table([_nmap_finding()])
        assert "NW-001" in html

    def test_ports_comma_joined_for_host(self) -> None:
        findings = [
            _nmap_finding(host="10.0.0.1", port="22"),
            _nmap_finding(host="10.0.0.1", port="443"),
        ]
        html = FindingsBuilder.build_comprehensive_network_table(findings)
        assert "22" in html
        assert "443" in html
        # Both ports on same host → comma-separated in one row.
        assert "22, 443" in html or "443, 22" in html

    def test_multiple_hosts_multiple_rows(self) -> None:
        findings = [
            _nmap_finding(host="10.0.0.1", port="80"),
            _nmap_finding(host="10.0.0.2", port="22"),
        ]
        html = FindingsBuilder.build_comprehensive_network_table(findings)
        assert "NW-001" in html
        assert "NW-002" in html
