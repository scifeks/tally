"""Integration test: Antares JSON -> normalize -> fingerprint -> persist."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.pipeline.fingerprint import compute_fingerprint
from domain.tools.base import ToolResult
from infrastructure.tools.parsers.antares import (
    AntaresHandler,
    parse_antares_json_string,
)

pytestmark = pytest.mark.integration

FIXTURE = Path("tests/fixtures/tools/antares_sweep_output.json")


class TestAntaresPipeline:
    def test_fixture_through_full_normalize(self) -> None:
        """Verify fixture parses, normalizes, and fingerprints correctly."""
        raw = FIXTURE.read_text()
        parsed = parse_antares_json_string(raw)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=raw,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-01-01T00:00:00Z",
            duration_seconds=120.5,
        )
        handler = AntaresHandler()
        rows = handler.normalize(result, "default")

        assert len(rows) == 3
        for row in rows:
            assert row["tool"] == "antares"
            assert row["severity"] in ("high", "medium", "low")
            assert row["confidence"] == "potential"
            fp = compute_fingerprint(row)
            assert fp  # non-empty fingerprint
            assert len(fp) == 64  # SHA256 hex

    def test_dedup_across_runs(self) -> None:
        """Verify fingerprints are stable for identical input."""
        raw = FIXTURE.read_text()
        parsed = parse_antares_json_string(raw)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=raw,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-01-01T00:00:00Z",
            duration_seconds=120.5,
        )
        handler = AntaresHandler()
        rows1 = handler.normalize(result, "default")
        rows2 = handler.normalize(result, "default")

        fps1 = [compute_fingerprint(r) for r in rows1]
        fps2 = [compute_fingerprint(r) for r in rows2]
        assert fps1 == fps2  # same input = same fingerprints

    def test_render_produces_indexable_text(self) -> None:
        """Verify render() produces valid ChromaDB indexable content."""
        raw = FIXTURE.read_text()
        parsed = parse_antares_json_string(raw)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=raw,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-01-01T00:00:00Z",
            duration_seconds=120.5,
        )
        handler = AntaresHandler()
        rows = handler.normalize(result, "default")
        for row in rows:
            rendered = handler.render(row)
            assert rendered.startswith("[antares]")
            assert len(rendered) > 20  # meaningful content

    def test_normalized_rows_have_required_fields(self) -> None:
        """Verify all normalized rows have required fields for storage."""
        raw = FIXTURE.read_text()
        parsed = parse_antares_json_string(raw)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=raw,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-01-01T00:00:00Z",
            duration_seconds=120.5,
        )
        handler = AntaresHandler()
        rows = handler.normalize(result, "default")

        required_fields = [
            "tool",
            "profile",
            "finding_type",
            "severity",
            "confidence",
            "rule_id",
            "file_path",
            "description",
            "cwe",
            "timestamp",
            "meta",
        ]
        for row in rows:
            for field in required_fields:
                assert field in row, f"Missing field {field} in row"
                assert row[field] is not None

    def test_fingerprint_differs_for_different_cwe(self) -> None:
        """Verify different CWEs produce different fingerprints."""
        raw = FIXTURE.read_text()
        parsed = parse_antares_json_string(raw)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=raw,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-01-01T00:00:00Z",
            duration_seconds=120.5,
        )
        handler = AntaresHandler()
        rows = handler.normalize(result, "default")

        fingerprints = [compute_fingerprint(r) for r in rows]
        # Should have unique fingerprints if they differ by CWE or file path
        assert len(fingerprints) == len(set(fingerprints))
