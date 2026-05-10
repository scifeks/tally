"""Unit tests for the shared prompt-injection fencing module."""

from __future__ import annotations

from application.triage.prompts._fencing import fence


class TestFence:
    def test_wraps_content_with_markers(self) -> None:
        result = fence("hello world", "test_label")
        lines = result.splitlines()
        assert lines[0] == "<<<TALLY_DATA_START: test_label>>>"
        assert lines[-1] == "<<<TALLY_DATA_END: test_label>>>"
        assert "hello world" in result

    def test_label_appears_in_both_markers(self) -> None:
        result = fence("data", "finding_metadata")
        assert "<<<TALLY_DATA_START: finding_metadata>>>" in result
        assert "<<<TALLY_DATA_END: finding_metadata>>>" in result

    def test_multiline_content_preserved(self) -> None:
        content = "line one\nline two\nline three"
        result = fence(content, "multi")
        assert content in result
