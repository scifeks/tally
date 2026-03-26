"""Integration tests for gitleaks git-scan via normalize() and render()."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.gitleaks_parser import (  # noqa: E402
    parse_gitleaks_json,
)

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
_TIMESTAMP = "2024-01-01T00:00:00"


def _parse_fixture(filename: str) -> dict:
    return parse_gitleaks_json(_FIXTURES / filename)


def _make_gitleaks_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="gitleaks",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@pytest.fixture()
def git_parsed_data() -> dict:
    return _parse_fixture("gitleaks_git.json")


class TestGitleaksGitScan:
    def test_count(self, git_parsed_data: dict) -> None:
        """Normalized row count matches number of git-scan secrets."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        n_secrets = len(git_parsed_data["secrets"])
        result = _make_gitleaks_result(git_parsed_data)
        rows = handler.normalize(result, profile="git-repo")
        assert len(rows) == n_secrets

    def test_commit_present_in_git_scan(self, git_parsed_data: dict) -> None:
        """Git-scan rows must have a non-empty 'commit' key."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(git_parsed_data)
        rows = handler.normalize(result, profile="git-repo")
        for row in rows:
            assert "commit" in row, f"'commit' key absent from git-scan row: {row}"
            assert row["commit"], f"'commit' value is empty in git-scan row: {row}"

    def test_content_accuracy_with_commit(self, git_parsed_data: dict) -> None:
        """Rendered text has correct content and commit is stored in row."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(git_parsed_data)
        rows = handler.normalize(result, profile="git-repo")
        for row in rows:
            text = handler.render(row)
            rule_id = row["rule_id"]
            file_path = row["file_path"]
            line_number = row["line_number"]
            assert (
                f"[gitleaks] Rule: {rule_id} | File: {file_path}:{line_number}"
            ) in text

        raw_fixture = json.load(open(_FIXTURES / "gitleaks_git.json"))
        commit_by_rule = {f["RuleID"]: f["Commit"] for f in raw_fixture}
        for row in rows:
            expected_commit = commit_by_rule.get(row["rule_id"])
            assert row.get("commit") == expected_commit, (
                f"Commit mismatch for rule {row['rule_id']!r}: "
                f"expected {expected_commit!r}, got {row.get('commit')!r}"
            )

    def test_metadata_fidelity(self, git_parsed_data: dict) -> None:
        """Git-scan row fields are correct; severity is always 'high'."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(git_parsed_data)
        rows = handler.normalize(result, profile="git-repo")
        for row in rows:
            assert row["tool"] == "gitleaks"
            assert row["profile"] == "git-repo"
            assert row["finding_type"] == '["secret"]'
            assert row["severity"] == "high", (
                f"severity must always be 'high', got {row['severity']!r}"
            )
            assert "commit" in row

    def test_no_duplicates(self, git_parsed_data: dict) -> None:
        """normalize() is deterministic — same input produces same count."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(git_parsed_data)
        rows_first = handler.normalize(result, profile="git-repo")
        rows_second = handler.normalize(result, profile="git-repo")
        assert len(rows_first) == len(rows_second)
