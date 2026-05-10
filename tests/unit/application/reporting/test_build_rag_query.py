"""Unit coverage for ``_build_rag_query`` against the ``critical-issues``
branch.

Regression: this branch previously called ``.get(field)`` on ``Finding``
objects, raising ``AttributeError`` mid-batch and breaking
``critical-issues`` for every project.
"""

from __future__ import annotations

from typing import Any

from application.reporting.draft_orchestrator import _build_rag_query
from domain.findings.entry import Finding


def _make_finding(
    finding_id: int,
    *,
    vulnerability_id: str | None = None,
    cwe: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        id=finding_id,
        fingerprint=None,
        run_id=None,
        tool=None,
        domain=None,
        segment=None,
        vulnerability_id=vulnerability_id,
        cwe=cwe or [],
        meta=meta or {},
    )


def test_critical_issues_extracts_vulnerability_id_cwe_and_meta_risk_type():
    findings = [
        _make_finding(
            1,
            vulnerability_id="CVE-2024-1111",
            cwe=["CWE-79"],
            meta={"risk_type": "XSS"},
        ),
        _make_finding(
            2,
            vulnerability_id="CVE-2024-2222",
            cwe=["CWE-89"],
            meta={"risk_type": "SQLi"},
        ),
    ]

    query = _build_rag_query("critical-issues", {"top_findings": findings})

    assert query is not None
    assert query.startswith("critical high severity vulnerabilities exploitable ")
    for term in ("CVE-2024-1111", "CVE-2024-2222", "CWE-79", "CWE-89", "XSS", "SQLi"):
        assert term in query


def test_critical_issues_dedupes_repeated_terms():
    findings = [
        _make_finding(1, vulnerability_id="CVE-2024-1111", cwe=["CWE-79"]),
        _make_finding(2, vulnerability_id="CVE-2024-1111", cwe=["CWE-79"]),
    ]

    query = _build_rag_query("critical-issues", {"top_findings": findings})

    assert query is not None
    assert query.count("CVE-2024-1111") == 1
    assert query.count("CWE-79") == 1


def test_critical_issues_with_no_findings_returns_base_only():
    query = _build_rag_query("critical-issues", {"top_findings": []})

    assert query == "critical high severity vulnerabilities exploitable"


def test_critical_issues_with_no_relevant_fields_returns_base_only():
    findings = [_make_finding(1), _make_finding(2)]

    query = _build_rag_query("critical-issues", {"top_findings": findings})

    assert query == "critical high severity vulnerabilities exploitable"


def test_critical_issues_skips_non_string_risk_type():
    findings = [
        _make_finding(1, vulnerability_id="CVE-X", meta={"risk_type": 42}),
    ]

    query = _build_rag_query("critical-issues", {"top_findings": findings})

    assert query is not None
    assert "CVE-X" in query
    assert "42" not in query


def test_critical_issues_handles_missing_top_findings_key():
    """Defensive: an empty/missing context key returns the base query."""
    query = _build_rag_query("critical-issues", {})

    assert query == "critical high severity vulnerabilities exploitable"
