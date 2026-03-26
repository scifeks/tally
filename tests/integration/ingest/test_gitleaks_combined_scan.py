"""Integration tests for gitleaks combined-scan via normalize()."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.gitleaks_parser import (  # noqa: E402
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


@pytest.fixture()
def combined_parsed_data(dir_parsed_data: dict, git_parsed_data: dict) -> dict:
    return combine_gitleaks_results(dir_parsed_data, git_parsed_data)


class TestGitleaksCombinedScan:
    def test_combined_count(self, combined_parsed_data: dict) -> None:
        """Normalized row count equals len(combined['secrets'])."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        n = len(combined_parsed_data["secrets"])
        result = _make_gitleaks_result(combined_parsed_data)
        rows = handler.normalize(result, profile="combined-repo")
        assert len(rows) == n

    def test_combined_metadata_fidelity(self, combined_parsed_data: dict) -> None:
        """Every normalized row matches a combined secret by rule+file+line."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(combined_parsed_data)
        rows = handler.normalize(result, profile="combined-repo")
        for row in rows:
            matching_secret = next(
                (
                    s
                    for s in combined_parsed_data["secrets"]
                    if s["rule_id"] == row["rule_id"]
                    and s["file_path"] == row["file_path"]
                    and s["line_number"] == row["line_number"]
                ),
                None,
            )
            assert matching_secret is not None, (
                f"No matching secret found for row {row}"
            )

    def test_deduplication_within_combined(
        self,
        dir_parsed_data: dict,
        git_parsed_data: dict,
    ) -> None:
        """The shared finding appears exactly once after combine."""
        combined = combine_gitleaks_results(dir_parsed_data, git_parsed_data)
        shared_entries = [
            s
            for s in combined["secrets"]
            if s["rule_id"] == "aws-access-token"
            and s["file_path"] == "config/aws.js"
            and s["line_number"] == 10
        ]
        assert len(shared_entries) == 1, (
            f"Expected 1 deduplicated entry, got {len(shared_entries)}"
        )
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(combined)
        rows = handler.normalize(result, profile="combined-repo")
        assert len(rows) == len(combined["secrets"]), (
            f"Normalized {len(rows)} != combined count {len(combined['secrets'])}"
        )
