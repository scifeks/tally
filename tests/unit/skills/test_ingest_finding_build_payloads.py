"""Unit tests for the ingest-finding skill's report-to-payload mapper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude/skills/ingest-finding/build_payloads.py"
)
_spec = importlib.util.spec_from_file_location("build_payloads", _SCRIPT)
assert _spec is not None and _spec.loader is not None
build_payloads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_payloads)

SECTION_MAP = {
    "What's wrong": "description",
    "Who can exploit it": "attack_vector",
    "Remediation": "meta.remediation",
}
HEADER_MAP = {"Repo": "meta.report_repo", "Status": "meta.report_status"}
CLASSIFICATION: dict[str, Any] = {
    "file": "src/a.php",
    "line_number": 3,
    "severity": "high",
    "confidence": "confirmed",
    "cwe": ["CWE-79"],
    "finding_type": ["vulnerability"],
    "rule_id": "xss-stored",
    "meta": {"owasp_name": "A03:2021 Injection"},
}
REPORT = (
    "# ABC-UI-12: Script in descriptions runs in the page\n"
    "\n"
    "- **Repo:** web\n"
    "- **Status:** Open, see WEB-TO-PDF-API-5 and VR-26010\n"
    "\n"
    "## What's wrong\n"
    "\n"
    'The `content` is set as "HTML" \\ unescaped.\n'
    "\n"
    "### Detail\n"
    "Uses UTF-8 and CWE-79, unlike ABC-UI-1.\n"
    "\n"
    "## Who can exploit it\n"
    "\n"
    "Dealer staff.\n"
)


def _build(
    report: str = REPORT,
    section_map: dict[str, str] | None = None,
    header_map: dict[str, str] | None = None,
    classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_payloads.build_payload(
        report,
        section_map=SECTION_MAP if section_map is None else section_map,
        header_map=HEADER_MAP if header_map is None else header_map,
        classification=CLASSIFICATION if classification is None else classification,
        not_refs=[],
    )


class TestBuildPayload:
    def test_maps_report_text_verbatim(self) -> None:
        payload = _build()

        assert payload["description"] == (
            'The `content` is set as "HTML" \\ unescaped.\n'
            "\n"
            "### Detail\n"
            "Uses UTF-8 and CWE-79, unlike ABC-UI-1."
        )
        assert payload["attack_vector"] == "Dealer staff."
        assert payload["meta"]["title"] == "Script in descriptions runs in the page"
        assert payload["meta"]["catalog_code"] == "ABC-UI-12"
        assert payload["meta"]["report_status"] == (
            "Open, see WEB-TO-PDF-API-5 and VR-26010"
        )
        assert payload["meta"]["remediation"] == build_payloads.NO_REMEDIATION
        assert payload["meta"]["owasp_name"] == "A03:2021 Injection"
        assert payload["severity"] == "high"

    def test_internal_refs_keep_multi_part_codes_and_drop_noise(self) -> None:
        assert _build()["meta"]["internal_refs"] == [
            "ABC-UI-1",
            "VR-26010",
            "WEB-TO-PDF-API-5",
        ]

    @pytest.mark.parametrize(
        ("report", "section_map", "header_map", "classification", "message"),
        [
            pytest.param(
                "Script in descriptions\n\n## What's wrong\n\nText\n",
                None,
                None,
                None,
                "first line",
                id="no-report-code",
            ),
            pytest.param(
                REPORT + "\n## Timeline\n\nLater\n",
                None,
                None,
                None,
                "'Timeline' is not in section_map",
                id="unmapped-section",
            ),
            pytest.param(
                REPORT.replace("- **Repo:**", "- **Owner:**"),
                None,
                None,
                None,
                "'Owner' is not in header_map",
                id="unmapped-header",
            ),
            pytest.param(
                REPORT.replace("- **Repo:** web\n", "Found during review.\n"),
                None,
                None,
                None,
                "before the first section",
                id="unmapped-preamble",
            ),
            pytest.param(
                REPORT,
                {**SECTION_MAP, "Who can exploit it": "meta.severity"},
                None,
                None,
                "would be dropped",
                id="reserved-meta-key",
            ),
            pytest.param(
                REPORT,
                {**SECTION_MAP, "Who can exploit it": "description"},
                None,
                None,
                "two parts of the report",
                id="two-sections-one-field",
            ),
            pytest.param(
                REPORT,
                {**SECTION_MAP, "What's wrong": "meta.summary"},
                None,
                None,
                "no section maps to description",
                id="no-description",
            ),
            pytest.param(
                REPORT,
                None,
                None,
                {**CLASSIFICATION, "description": "Rewritten"},
                "report text field",
                id="classification-overwrites-text",
            ),
            pytest.param(
                REPORT,
                None,
                None,
                {**CLASSIFICATION, "meta": {"report_repo": "other"}},
                "classification sets meta.report_repo",
                id="classification-overwrites-meta",
            ),
        ],
    )
    def test_refuses_reports_it_cannot_map_faithfully(
        self,
        report: str,
        section_map: dict[str, str] | None,
        header_map: dict[str, str] | None,
        classification: dict[str, Any] | None,
        message: str,
    ) -> None:
        with pytest.raises(build_payloads.ReportError, match=message):
            _build(report, section_map, header_map, classification)
