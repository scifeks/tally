"""E2E tests for DefectDojo export against a live instance.

Requires DefectDojo running at 127.0.0.1:8080.
"""

from __future__ import annotations

import os

import httpx
import pytest

from core.config.schemas.defectdojo_config import (
    DefectDojoConnectionConfig,
    DefectDojoProjectConfig,
)
from domain.findings.entry import Finding
from infrastructure.export.defectdojo.adapter import (
    DefectDojoExportAdapter,
)
from tests.conftest import requires_defectdojo

pytestmark = [pytest.mark.e2e, requires_defectdojo]

_DD_URL = os.environ.get("DD_TEST_URL", "http://127.0.0.1:8080")
_DD_TOKEN = os.environ.get("DD_TEST_TOKEN", "")
_PRODUCT = "Tally E2E Test"
_ENGAGEMENT = "Export E2E"


def _build_connection() -> DefectDojoConnectionConfig:
    return DefectDojoConnectionConfig(
        url=_DD_URL,
        api_token=_DD_TOKEN,
    )


def _build_project() -> DefectDojoProjectConfig:
    return DefectDojoProjectConfig(
        product_name=_PRODUCT,
        engagement_name=_ENGAGEMENT,
    )


def _query_dd_findings(product_name: str) -> dict:
    resp = httpx.get(
        f"{_DD_URL}/api/v2/findings/",
        headers={"Authorization": f"Token {_DD_TOKEN}"},
        params={"test__engagement__product__name": product_name},
        verify=False,
        timeout=30,
    )
    return resp.json()


def _make_finding(
    finding_id: int,
    tool: str = "semgrep",
    **overrides,
) -> Finding:
    defaults = {
        "id": finding_id,
        "fingerprint": f"e2e-{tool}-{finding_id}",
        "run_id": 1,
        "tool": tool,
        "domain": "code",
        "segment": "sast",
        "finding_type": ["vulnerability"],
        "severity": "high",
        "confidence": "confirmed",
        "file": "src/app.py",
        "rule_id": f"e2e-rule-{finding_id}",
        "url": None,
        "vulnerability_id": None,
        "package_name": None,
        "ecosystem": None,
        "description": f"E2E test finding {finding_id}",
        "package_version": None,
        "cwe": ["CWE-79"],
        "enriched": True,
        "meta": {
            "line_start": finding_id * 10,
            "title": f"E2E Finding {finding_id}",
        },
        "first_seen": "2024-01-15T10:00:00",
        "last_seen": "2024-01-15T10:00:00",
        "seen_count": 1,
        "status": "active",
    }
    defaults.update(overrides)
    return Finding(**defaults)


class TestDefectDojoExportE2E:
    def test_connection(self) -> None:
        adapter = DefectDojoExportAdapter(_build_connection(), _build_project())
        assert adapter.test_connection() is True

    def test_export_single_finding(self) -> None:
        adapter = DefectDojoExportAdapter(_build_connection(), _build_project())
        finding = _make_finding(1)
        result = adapter.export_findings([finding])

        assert result.success is True
        assert result.findings_exported == 1
        assert result.findings_failed == 0
        assert result.errors == ()

    def test_export_multiple_tools(self) -> None:
        adapter = DefectDojoExportAdapter(_build_connection(), _build_project())
        findings = [
            _make_finding(101, tool="semgrep"),
            _make_finding(
                102,
                tool="zap",
                domain="web",
                segment="web",
                file=None,
                url="http://example.com/login",
                meta={"title": "XSS on login", "param": "q"},
            ),
            _make_finding(
                103,
                tool="osv",
                segment="sca",
                package_name="lodash",
                package_version="4.17.20",
                vulnerability_id="CVE-2021-23337",
                meta={
                    "title": "Lodash command injection",
                    "fixed_version": "4.17.21",
                },
            ),
            _make_finding(
                104,
                tool="garak",
                domain="llm",
                segment="llm",
                file=None,
                meta={
                    "title": "Prompt injection bypass",
                    "probe": "garak.probes.dan.DAN",
                    "detector": "garak.detectors.mitigation.MitigationBypass",
                    "probe_description": "DAN jailbreak",
                    "goal": "Bypass safety",
                    "fail_rate": 0.4,
                },
            ),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        assert result.findings_exported == 4
        assert result.findings_failed == 0

    def test_reimport_deduplicates(self) -> None:
        adapter = DefectDojoExportAdapter(
            _build_connection(),
            _build_project(),
        )
        finding = _make_finding(200, fingerprint="dedup-test-fixed")

        result1 = adapter.export_findings([finding])
        assert result1.success is True

        data_before = _query_dd_findings(_PRODUCT)
        count_before = data_before["count"]

        result2 = adapter.export_findings([finding])
        assert result2.success is True

        data_after = _query_dd_findings(_PRODUCT)
        count_after = data_after["count"]

        assert count_after == count_before
