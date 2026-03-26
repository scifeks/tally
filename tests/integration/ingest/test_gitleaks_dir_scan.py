"""Integration tests for gitleaks GitleaksChunkBuilder.normalize() and render()."""

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


class TestGitleaksDirScan:
    def test_count(self, dir_parsed_data: dict) -> None:
        """Normalized row count matches number of secrets in fixture."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        n_secrets = len(dir_parsed_data["secrets"])
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == n_secrets

    def test_identity(self, dir_parsed_data: dict) -> None:
        """Every normalized row has required identifying fields."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert rows
        for row in rows:
            assert "rule_id" in row
            assert "file_path" in row
            assert "line_number" in row

    def test_metadata_fidelity(self, dir_parsed_data: dict) -> None:
        """Every metadata field matches the expected value from the fixture."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        assert len(rows) == len(dir_parsed_data["secrets"])

        for i, (row, secret) in enumerate(zip(rows, dir_parsed_data["secrets"])):
            tags_str = ", ".join(secret.get("tags") or [])
            expected = {
                "tool": "gitleaks",
                "profile": "test-repo",
                "finding_type": '["secret"]',
                "severity": "high",
                "confidence": "confirmed",
                "rule_id": secret["rule_id"],
                "file_path": secret["file_path"],
                "line_number": secret["line_number"],
                "tags": tags_str,
                "source_file": "",
            }
            for field, expected_val in expected.items():
                assert row.get(field) == expected_val, (
                    f"Secret #{i}: field {field!r} mismatch. "
                    f"Expected {expected_val!r}, got {row.get(field)!r}"
                )
            assert "timestamp" in row, f"Secret #{i}: 'timestamp' absent from row"

    def test_content_accuracy(self, dir_parsed_data: dict) -> None:
        """Rendered text matches the expected template."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")

        for row in rows:
            text = handler.render(row)
            rule_id = row["rule_id"]
            file_path = row["file_path"]
            line_number = row["line_number"]
            assert (
                f"[gitleaks] Rule: {rule_id} | File: {file_path}:{line_number}"
            ) in text

    def test_no_commit_in_dir_scan(self, dir_parsed_data: dict) -> None:
        """Dir-scan rows must NOT have a 'commit' key."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert "commit" not in row, (
                f"'commit' key must be absent from dir-scan row, got: {row}"
            )

    def test_no_duplicates(self, dir_parsed_data: dict) -> None:
        """normalize() is deterministic — same input produces same count."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows_first = handler.normalize(result, profile="test-repo")
        rows_second = handler.normalize(result, profile="test-repo")
        assert len(rows_first) == len(rows_second)

    def test_empty_findings(self) -> None:
        """Ingesting an empty secrets list → 0 rows."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        empty_data: dict = {
            "secrets": [],
            "summary": {
                "total_secrets": 0,
                "by_rule": {},
                "files_with_secrets": 0,
            },
        }
        result = _make_gitleaks_result(empty_data)
        rows = handler.normalize(result, profile="test-repo")
        assert rows == []

    def test_ingest_replaces_stale(self, dir_parsed_data: dict) -> None:
        """normalize() sets profile correctly; different profiles are independent."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows_a = handler.normalize(result, profile="profile-a")
        rows_b = handler.normalize(result, profile="profile-b")
        assert all(r["profile"] == "profile-a" for r in rows_a)
        assert all(r["profile"] == "profile-b" for r in rows_b)

    def test_shared_metadata_fields(self, dir_parsed_data: dict) -> None:
        """Gitleaks rows have correct domain/enriched/type_* fields."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            assert row["domain"] == "code"
            assert row["enriched"] is False
            assert row["type_secret"] is True
            assert row["type_vulnerability"] is False
            assert row["type_weakness"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_exposure"] is False
            assert row["type_dependency"] is False

    def test_text_no_match_value(self, dir_parsed_data: dict) -> None:
        """Rendered text must not have 'Pattern matched'; must have rule prefix."""
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        result = _make_gitleaks_result(dir_parsed_data)
        rows = handler.normalize(result, profile="test-repo")
        for row in rows:
            text = handler.render(row)
            assert "Pattern matched" not in text
            assert "[gitleaks] Rule:" in text
