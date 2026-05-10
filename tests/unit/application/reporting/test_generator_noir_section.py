"""Tests for Noir 'Discovered Attack Surface' section in ReportGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.reporting.generator import ReportGenerator

_NOIR_FINDINGS = [
    {
        "tool": "noir",
        "method": "GET",
        "url": "/api/users",
        "file": "src/routes/users.js",
        "description": "Endpoint GET /api/users, params: page, limit",
        "severity": "informational",
        "finding_type": ["informational"],
    },
    {
        "tool": "noir",
        "method": "POST",
        "url": "/api/users",
        "file": "src/routes/users.js",
        "description": "Endpoint POST /api/users",
        "severity": "informational",
        "finding_type": ["informational"],
    },
    {
        "tool": "noir",
        "method": "GET",
        "url": "/learn/vulnerability/:vuln",
        "file": None,
        "description": "Endpoint GET /learn/vulnerability/:vuln, params: vuln",
        "severity": "informational",
        "finding_type": ["informational"],
    },
]


def _make_generator(findings_by_tool: dict) -> ReportGenerator:
    finding_repo = MagicMock()

    all_findings = []
    for tool_findings in findings_by_tool.values():
        for f in tool_findings:
            row = dict(f)
            row.setdefault("meta", {})
            all_findings.append(row)

    finding_repo.get_all_findings_deserialized.return_value = all_findings
    return ReportGenerator(
        rag_engine=MagicMock(),
        project="test-proj",
        finding_repo=finding_repo,
    )


class TestReportGeneratorNoirMarkdown:
    def _report(self, findings: list[dict] | None = None) -> str:
        f = findings if findings is not None else _NOIR_FINDINGS
        gen = _make_generator({"noir": f})
        return gen.generate(output_format="markdown")

    def test_noir_path_param_uri_present(self) -> None:
        report = self._report()
        assert "/learn/vulnerability/:vuln" in report

    def test_noir_not_rendered_as_vulnerability(self) -> None:
        report = self._report()
        noir_section_start = report.find("Discovered Attack Surface")
        assert noir_section_start != -1
        # The section must not contain a severity column header like a vuln table
        noir_section = report[noir_section_start:]
        assert "| Severity |" not in noir_section

    def test_no_noir_section_when_no_noir_findings(self) -> None:
        gen = _make_generator({"zap": []})
        report = gen.generate(output_format="markdown")
        assert "Discovered Attack Surface" not in report

    def test_noir_section_note_present(self) -> None:
        """A clarifying note must appear to distinguish from vulnerability findings."""
        report = self._report()
        assert "informational" in report.lower()
        assert "not vulnerability" in report.lower()


class TestReportGeneratorNoirHtml:
    def _report(self, findings: list[dict] | None = None) -> str:
        f = findings if findings is not None else _NOIR_FINDINGS
        gen = _make_generator({"noir": f})
        return gen.generate(output_format="html")

    def test_no_noir_section_when_empty(self) -> None:
        gen = _make_generator({"noir": []})
        report = gen.generate(output_format="html")
        assert "Discovered Attack Surface" not in report
