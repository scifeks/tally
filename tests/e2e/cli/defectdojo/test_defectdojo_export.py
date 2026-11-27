"""E2E tests for DefectDojo export against a live instance.

Requires DefectDojo running at 127.0.0.1:8080.
"""

from __future__ import annotations

import os

import httpx
import pytest

from application.ports.export import SyncBatch
from core.config.schemas.defectdojo_config import (
    DefectDojoGlobalConfig,
)
from domain.findings.entry import Finding
from infrastructure.export.defectdojo.adapter import (
    DefectDojoExportAdapter,
)
from tests.conftest import requires_defectdojo

pytestmark = [pytest.mark.e2e, requires_defectdojo]

_DD_URL = os.environ.get("DD_TEST_URL", "http://127.0.0.1:8080")
_DD_TOKEN = os.environ.get("DD_TEST_TOKEN", "")
_PROJECT = "e2e-sync"
_ORGANIZATION = "E2E Sync Org"
_ENGAGEMENT = "Export E2E"
_PRODUCT = f"{_PROJECT} / e2e-repo"
_HEADERS = {"Authorization": f"Token {_DD_TOKEN}"}


def _build_config() -> DefectDojoGlobalConfig:
    return DefectDojoGlobalConfig(
        url=_DD_URL,
        api_token=_DD_TOKEN,
    )


def _build_adapter() -> DefectDojoExportAdapter:
    return DefectDojoExportAdapter(
        config=_build_config(),
        repo_names={1: "e2e-repo"},
        project_name=_PROJECT,
        organization_name=_ORGANIZATION,
        engagement_name=_ENGAGEMENT,
    )


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(
        f"{_DD_URL}/api/v2/{path}",
        headers=_HEADERS,
        params=params,
        verify=False,
        timeout=30,
    )
    return resp.json()


def _query_dd_findings(product_name: str) -> dict:
    return _get("findings/", {"test__engagement__product__name": product_name})


def _batches(findings: list[Finding]) -> list[SyncBatch]:
    by_tool: dict[str, list[Finding]] = {}
    for finding in findings:
        by_tool.setdefault(finding.tool or "", []).append(finding)
    return [SyncBatch(1, tool, tuple(group)) for tool, group in by_tool.items()]


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
        "repo_id": 1,
    }
    defaults.update(overrides)
    return Finding(**defaults)


class TestDefectDojoExportE2E:
    def test_connection(self) -> None:
        adapter = _build_adapter()
        assert adapter.test_connection() is True

    def test_export_single_finding(self) -> None:
        adapter = _build_adapter()
        finding = _make_finding(1)
        result = adapter.export_batches(_batches([finding]))

        assert result.success is True
        assert result.findings_exported == 1
        assert result.findings_failed == 0
        assert result.errors == ()

    def test_export_multiple_tools(self) -> None:
        adapter = _build_adapter()
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
        result = adapter.export_batches(_batches(findings))

        assert result.success is True
        assert result.findings_exported == 4
        assert result.findings_failed == 0

    def test_reimport_deduplicates(self) -> None:
        adapter = _build_adapter()
        finding = _make_finding(200, fingerprint="dedup-test-fixed")

        product = _PRODUCT

        result1 = adapter.export_batches(_batches([finding]))
        assert result1.success is True

        data_before = _query_dd_findings(product)
        count_before = data_before["count"]

        result2 = adapter.export_batches(_batches([finding]))
        assert result2.success is True

        data_after = _query_dd_findings(product)
        count_after = data_after["count"]

        assert count_after == count_before

    def test_hierarchy_and_engagement_type(self) -> None:
        result = _build_adapter().export_batches(_batches([_make_finding(300)]))
        assert result.success is True

        product = _get("products/", {"name": _PRODUCT})["results"][0]
        organization = _get(f"product_types/{product['prod_type']}/")
        engagements = _get("engagements/", {"product": product["id"]})["results"]

        assert organization["name"] == _ORGANIZATION
        assert [e["engagement_type"] for e in engagements] == ["Interactive"]
