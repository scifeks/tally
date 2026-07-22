"""Tests for LLM scan handler implementations."""

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.claudecode import ClaudeCodeScanHandler


class TestClaudeCodeScanHandler:
    def test_normalize_extracts_findings(self) -> None:
        handler = ClaudeCodeScanHandler()
        result = ToolResult(
            tool_name="claudecode",
            success=True,
            output="",
            parsed_data={
                "findings": [
                    {
                        "file_path": "src/app.py",
                        "line_number": 42,
                        "description": "SQL injection via string concat",
                        "severity": "high",
                        "confidence": "confirmed",
                        "finding_type": ["vulnerability"],
                        "segment": "sast",
                        "reasoning": "Direct user input in query",
                        "remediation": "Use parameterized queries",
                    }
                ]
            },
            output_files={},
            timestamp="2026-07-22T00:00:00",
            duration_seconds=60.0,
        )
        rows = handler.normalize(result, "my-repo")
        assert len(rows) == 1
        assert rows[0]["tool"] == "claudecode"
        assert rows[0]["domain"] == "llm"
        assert rows[0]["severity"] == "high"
        assert rows[0]["file_path"] == "src/app.py"
        assert rows[0]["profile"] == "my-repo"

    def test_normalize_empty_parsed_data(self) -> None:
        handler = ClaudeCodeScanHandler()
        result = ToolResult(
            tool_name="claudecode",
            success=True,
            output="",
            parsed_data={},
            output_files={},
            timestamp="2026-07-22T00:00:00",
            duration_seconds=0.0,
        )
        rows = handler.normalize(result, "repo")
        assert rows == []

    def test_render_includes_key_fields(self) -> None:
        handler = ClaudeCodeScanHandler()
        row = {
            "tool": "claudecode",
            "file_path": "src/app.py",
            "severity": "high",
            "description": "SQL injection",
            "rule_id": "sql-injection-concat",
        }
        text = handler.render(row)
        assert "[claudecode]" in text
        assert "src/app.py" in text
        assert "SQL injection" in text

    def test_fingerprint_key_stable(self) -> None:
        handler = ClaudeCodeScanHandler()
        finding = {
            "tool": "claudecode",
            "file_path": "src/app.py",
            "line_start": 42,
            "rule_id": "sql-injection",
        }
        key = handler.fingerprint_key(finding)
        assert key == handler.fingerprint_key(finding)
        assert "claudecode" in key
        assert "src/app.py" in key

    def test_handler_properties(self) -> None:
        handler = ClaudeCodeScanHandler()
        assert handler.tool_name == "claudecode"
        assert handler.domain == "llm"
        assert handler.should_enrich is False
        assert handler.should_visualize is True
