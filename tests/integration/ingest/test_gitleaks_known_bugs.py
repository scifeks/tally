"""Integration tests for known gitleaks ingestion behaviors."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.gitleaks import (  # noqa: E402
    combine_gitleaks_results,
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
def dir_parsed_data() -> dict:
    return _parse_fixture("gitleaks_dir.json")


@pytest.fixture()
def git_parsed_data() -> dict:
    return _parse_fixture("gitleaks_git.json")


class TestKnownBugs:
    def test_combine_dedup_dir_git_shared_finding(
        self, dir_parsed_data: dict, git_parsed_data: dict
    ) -> None:
        """combine_gitleaks_results() deduplicates by (rule_id, file_path, line_number).

        The same secret from dir-scan and git-scan collapses to one entry.
        """
        combined = combine_gitleaks_results(dir_parsed_data, git_parsed_data)
        shared = [
            s
            for s in combined["secrets"]
            if s["rule_id"] == "aws-access-token"
            and s["file_path"] == "config/aws.js"
            and s["line_number"] == 10
        ]
        assert len(shared) == 1, (
            f"Expected 1 deduplicated entry for aws-access-token, got {len(shared)}."
        )

    def test_fingerprint_present_in_metadata(self, dir_parsed_data: dict) -> None:
        """normalize() stores the Fingerprint field in the row."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert rows, "No rows were produced"
        for row in rows:
            assert "fingerprint" in row, f"'fingerprint' key missing from row: {row}"
            assert row["fingerprint"], "fingerprint value must not be empty"
