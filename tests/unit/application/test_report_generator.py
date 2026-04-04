"""Unit tests for ReportGenerator (application.reporting.generator)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.reporting.generator import ReportGenerator


def _finding(**kwargs: object) -> dict[str, Any]:
    """Return a minimal deserialized finding dict."""
    return dict(kwargs)  # type: ignore[arg-type]


_GITLEAKS_FINDING = _finding(
    tool="gitleaks",
    severity="high",
    rule_id="aws-key",
    file="/src/main.py",
    file_path="/src/main.py",
    line_number=10,
)


@pytest.fixture()
def mock_engine() -> MagicMock:
    engine = MagicMock()
    return engine


@pytest.fixture()
def mock_finding_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_all_findings_deserialized.return_value = []
    return repo


@pytest.fixture()
def generator(mock_engine: MagicMock, mock_finding_repo: MagicMock) -> ReportGenerator:
    return ReportGenerator(
        mock_engine, project="test-project", finding_repo=mock_finding_repo
    )


class TestReportGenerator:
    def test_generate_unknown_format_raises(self, generator: ReportGenerator) -> None:
        with pytest.raises(ValueError, match="xml"):
            generator.generate(output_format="xml")

    def test_generate_returns_string(self, generator: ReportGenerator) -> None:
        result = generator.generate()
        assert isinstance(result, str)

    def test_generate_markdown_contains_header(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _GITLEAKS_FINDING
        ]
        result = generator.generate(output_format="markdown")
        assert "# Tally Security Report: test-project" in result

    def test_generate_markdown_contains_gitleaks_section(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _GITLEAKS_FINDING
        ]
        result = generator.generate(output_format="markdown")
        assert "### Secrets (gitleaks)" in result

    def test_generate_html_contains_doctype(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _GITLEAKS_FINDING
        ]
        result = generator.generate(output_format="html")
        assert result.startswith("<!DOCTYPE html>")

    def test_generate_html_contains_project_name(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _GITLEAKS_FINDING
        ]
        result = generator.generate(output_format="html")
        assert "test-project" in result

    def test_generate_json_is_valid_json(self, generator: ReportGenerator) -> None:
        result = generator.generate(output_format="json")
        json.loads(result)

    def test_generate_json_structure(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _finding(
                tool="semgrep",
                severity="medium",
                rule_id="sqli",
                file="/app/db.py",
                file_path="/app/db.py",
                line_start=5,
                cwe="CWE-89",
            )
        ]
        result = generator.generate(output_format="json")
        data = json.loads(result)
        assert data["project_name"] == "test-project"
        assert data["summary"]["total_findings"] == 1
        assert data["summary"]["by_tool"]["semgrep"] == 1
        assert "semgrep" in data["findings"]

    def test_generate_writes_file_when_output_path_given(
        self, generator: ReportGenerator, tmp_path: Path
    ) -> None:
        result = generator.generate(
            output_format="markdown",
            output_path=str(tmp_path / "report.md"),
        )
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "report.md").read_text() == result

    def test_aggregate_empty_repo_returns_zero_totals(
        self, generator: ReportGenerator
    ) -> None:
        result = generator._aggregate_findings()
        assert result["summary"]["total_findings"] == 0
        assert result["summary"]["by_tool"] == {}

    def test_aggregate_groups_by_tool(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _finding(tool="gitleaks", severity="high"),
            _finding(tool="gitleaks", severity="medium"),
            _finding(tool="semgrep", severity="low"),
        ]
        result = generator._aggregate_findings()
        assert result["summary"]["by_tool"]["gitleaks"] == 2
        assert result["summary"]["by_tool"]["semgrep"] == 1

    def test_aggregate_counts_severity(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.return_value = [
            _finding(tool="gitleaks", severity="high"),
            _finding(tool="semgrep", severity="critical"),
        ]
        result = generator._aggregate_findings()
        assert result["summary"]["by_severity"]["high"] == 1
        assert result["summary"]["by_severity"]["critical"] == 1

    def test_aggregate_repo_exception_logs_warning_and_returns_zeros(
        self, generator: ReportGenerator, mock_finding_repo: MagicMock
    ) -> None:
        mock_finding_repo.get_all_findings_deserialized.side_effect = RuntimeError(
            "db error"
        )
        result = generator._aggregate_findings()
        assert result["summary"]["total_findings"] == 0
