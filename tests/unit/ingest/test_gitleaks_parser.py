"""Unit tests for the gitleaks output parser (_parse_secret, parse_gitleaks_json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.tools.parsers.gitleaks_parser import (
    _parse_secret,
    parse_gitleaks_json,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


@pytest.fixture()
def raw_dir_findings() -> list:
    """Raw JSON array from gitleaks_dir.json — no parse_gitleaks_json() involved."""
    return json.loads((_FIXTURES / "gitleaks_dir.json").read_text())


@pytest.fixture()
def raw_git_findings() -> list:
    """Raw JSON array from gitleaks_git.json — no parse_gitleaks_json() involved."""
    return json.loads((_FIXTURES / "gitleaks_git.json").read_text())


class TestGitleaksParser:
    """Verify every field mapping in _parse_secret() against real fixture data."""

    def test_field_mapping_rule_id(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["rule_id"] == raw["RuleID"]

    def test_field_mapping_file_path(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["file_path"] == raw["File"]

    def test_field_mapping_line_number(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["line_number"] == raw["StartLine"]

    def test_field_mapping_description(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["description"] == raw["Description"]

    def test_field_mapping_tags_list_preserved(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["tags"] == (raw["Tags"] or [])

    def test_field_mapping_commit_git_scan(self, raw_git_findings: list) -> None:
        """Non-empty Commit from git scan is preserved as-is."""
        raw = raw_git_findings[0]
        assert raw["Commit"], "git fixture must have a non-empty Commit"
        parsed = _parse_secret(raw)
        assert parsed["commit"] == raw["Commit"]

    def test_commit_empty_string_becomes_none(self) -> None:
        """Commit='' from a dir scan must be stored as None, not empty string."""
        finding = {
            "RuleID": "aws-access-token",
            "File": "config/aws.js",
            "StartLine": 10,
            "Commit": "",
            "Secret": "AKIAZ3XYMWQ2LR7NVBPA",
            "Match": "AKIAZ3XYMWQ2LR7NVBPA",
            "Description": "test",
            "Tags": [],
        }
        parsed = _parse_secret(finding)
        assert parsed["commit"] is None, (
            f"Empty Commit string must map to None, got {parsed['commit']!r}"
        )

    def test_tags_none_becomes_empty_list(self) -> None:
        """Tags=null in raw JSON must become an empty list, not None."""
        finding = {
            "RuleID": "x",
            "File": "f.py",
            "StartLine": 1,
            "Commit": "",
            "Secret": "abc",
            "Match": "",
            "Description": "",
            "Tags": None,
        }
        parsed = _parse_secret(finding)
        assert parsed["tags"] == [], f"Tags=null must map to [], got {parsed['tags']!r}"

    def test_summary_counts(self) -> None:
        """parse_gitleaks_json summary.total_secrets matches len of raw array."""
        raw = json.loads((_FIXTURES / "gitleaks_dir.json").read_text())
        parsed = parse_gitleaks_json(_FIXTURES / "gitleaks_dir.json")
        assert parsed["summary"]["total_secrets"] == len(raw), (
            f"summary.total_secrets {parsed['summary']['total_secrets']} "
            f"!= raw finding count {len(raw)}"
        )
