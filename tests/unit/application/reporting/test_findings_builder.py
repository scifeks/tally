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
    """Return a minimal code finding dict with optional overrides.

    Field shapes match ``asdict(domain.findings.entry.Finding)``: ``meta``
    is a ``dict``, ``cwe`` is a ``list``. The reporting builder consumes
    the assembler's output, which is always asdict-shaped.
    """
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
        "meta": {},
        "package_name": None,
        "package_version": None,
        "ecosystem": None,
        "domain": "code",
        "segment": "sast",
        "url": None,
        "cwe": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# TestBuildMasterTable
# ---------------------------------------------------------------------------


class TestBuildMasterTable:
    def test_empty_code_findings_renders_placeholder(self) -> None:
        html = FindingsBuilder().build_master_table([])
        assert "placeholder" in html
        assert "No code findings" in html

    def test_code_finding_tal_id_appears(self) -> None:
        html = FindingsBuilder().build_master_table([_finding()])
        assert "TAL-001" in html

    def test_missing_tal_id_renders_dash(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(tal_id=None)])
        assert "—" in html

    def test_recurring_row_gets_css_class(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(seen_count=3)])
        assert "recurring-row" in html

    def test_non_recurring_row_lacks_css_class(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(seen_count=1)])
        assert "recurring-row" not in html

    def test_severity_badge_present(self) -> None:
        html = FindingsBuilder().build_master_table([_finding(severity="high")])
        assert "severity-badge" in html
        assert "high" in html

    def test_code_heading_present(self) -> None:
        html = FindingsBuilder().build_master_table([_finding()])
        assert "Code Findings" in html


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
        html = FindingsBuilder.build_code_cards(
            [_finding(segment="sast", file="src/foo.py", meta={"line_start": 42})]
        )
        assert "src/foo.py" in html
        assert "42" in html

    def test_secrets_location_shows_file(self) -> None:
        html = FindingsBuilder.build_code_cards(
            [_finding(segment="secrets", file="config/secrets.env")]
        )
        assert "config/secrets.env" in html

    def test_api_location_shows_method_and_url(self) -> None:
        html = FindingsBuilder.build_code_cards(
            [
                _finding(
                    segment="api",
                    url="https://example.com/login",
                    meta={"method": "POST"},
                )
            ]
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
        html = FindingsBuilder.build_code_cards(
            [_finding(meta={"title": "<script>xss</script>"})]
        )
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
        html = FindingsBuilder.build_secrets_cards(
            [_finding(segment="secrets", file=".env", meta={"line_number": 99})]
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
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(meta={"owasp_name": "Injection"})]
        )
        assert "Injection" in html

    def test_owasp_falls_back_to_cwe(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(cwe=["CWE-89"])]
        )
        assert "CWE-89" in html

    def test_owasp_falls_back_to_rule_id(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(cwe=[], rule_id="custom-rule")]
        )
        assert "custom-rule" in html

    def test_owasp_falls_back_to_unclassified(self) -> None:
        html = FindingsBuilder().build_comprehensive_code_table(
            [_finding(cwe=[], rule_id=None, meta={})]
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
