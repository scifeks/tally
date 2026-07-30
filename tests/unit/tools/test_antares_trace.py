"""Unit tests for Antares trace parsing and summarization."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.antares_trace import (
    build_trace_detail,
    build_trace_summary,
    locate_trace_files,
    parse_trace_file,
)


class TestParseTraceFile:
    """Test trace file parsing."""

    def test_parses_jsonl_events(self, tmp_path: Path) -> None:
        """Parse JSONL file with multiple events."""
        trace_file = tmp_path / "test.jsonl"
        events_data = [
            {"timestamp": 1.0, "phase": "tool_call", "payload": {}, "evidence_id": "1"},
            {
                "timestamp": 2.0,
                "phase": "tool_result",
                "payload": {},
                "evidence_id": "1",
            },
            {"timestamp": 3.0, "phase": "done", "payload": {}, "evidence_id": None},
        ]
        with open(trace_file, "w", encoding="utf-8") as f:
            for event in events_data:
                f.write(json.dumps(event) + "\n")

        result = parse_trace_file(trace_file)

        assert len(result) == 3
        assert result[0]["phase"] == "tool_call"
        assert result[1]["phase"] == "tool_result"
        assert result[2]["phase"] == "done"

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        """Skip malformed JSON lines without crashing."""
        trace_file = tmp_path / "test.jsonl"
        with open(trace_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp": 1.0, "phase": "tool_call"}\n')
            f.write("not valid json\n")
            f.write('{"timestamp": 2.0, "phase": "done"}\n')

        result = parse_trace_file(trace_file)

        assert len(result) == 2
        assert result[0]["phase"] == "tool_call"
        assert result[1]["phase"] == "done"

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        """Parse empty file returns empty list."""
        trace_file = tmp_path / "empty.jsonl"
        trace_file.write_text("")

        result = parse_trace_file(trace_file)

        assert result == []

    def test_file_not_found_returns_empty_list(self, tmp_path: Path) -> None:
        """Non-existent file returns empty list."""
        trace_file = tmp_path / "missing.jsonl"

        result = parse_trace_file(trace_file)

        assert result == []

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        """Skip blank lines between events."""
        trace_file = tmp_path / "test.jsonl"
        with open(trace_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp": 1.0, "phase": "tool_call"}\n')
            f.write("\n")
            f.write("   \n")
            f.write('{"timestamp": 2.0, "phase": "done"}\n')

        result = parse_trace_file(trace_file)

        assert len(result) == 2


class TestBuildTraceSummary:
    """Test trace summary generation."""

    def test_empty_events_returns_empty_string(self) -> None:
        """Empty events list returns empty string."""
        summary = build_trace_summary([])
        assert summary == ""

    def test_includes_tool_calls(self) -> None:
        """Summary includes tool calls section."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_call",
                "payload": {
                    "tool_name": "grep",
                    "arguments": {"pattern": "eval"},
                },
                "evidence_id": "1",
            },
        ]

        summary = build_trace_summary(events)

        assert "Tools used:" in summary
        assert "grep" in summary

    def test_includes_findings(self) -> None:
        """Summary includes findings section."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "finding",
                "payload": {
                    "title": "Code injection",
                    "cwe_id": "CWE-95",
                    "severity": "high",
                    "file_path": "src/app.py",
                },
                "evidence_id": None,
            },
        ]

        summary = build_trace_summary(events)

        assert "Findings:" in summary
        assert "Code injection" in summary
        assert "CWE-95" in summary

    def test_includes_messages(self) -> None:
        """Summary includes analysis messages."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "message",
                "payload": {"role": "assistant", "content": "Found security issue"},
                "evidence_id": None,
            },
        ]

        summary = build_trace_summary(events)

        assert "Analysis:" in summary
        assert "Found security issue" in summary

    def test_capped_at_5000_chars(self) -> None:
        """Summary is capped at 5000 characters."""
        events = []
        long_message = "This is a detailed analysis message. " * 200
        for i in range(20):
            events.append(
                {
                    "timestamp": float(i),
                    "phase": "message",
                    "payload": {
                        "role": "assistant",
                        "content": long_message,
                    },
                    "evidence_id": None,
                }
            )

        summary = build_trace_summary(events)

        assert len(summary) <= 5000
        if len(summary) >= 4997:
            assert summary.endswith("...")

    def test_limits_tool_calls_display(self) -> None:
        """Summary limits tool calls to first 5."""
        events = [
            {
                "timestamp": float(i),
                "phase": "tool_call",
                "payload": {"tool_name": f"tool_{i}", "arguments": {}},
                "evidence_id": str(i),
            }
            for i in range(10)
        ]

        summary = build_trace_summary(events)

        assert "and 5 more tool calls" in summary

    def test_limits_messages_display(self) -> None:
        """Summary limits messages to first 3."""
        events = [
            {
                "timestamp": float(i),
                "phase": "message",
                "payload": {"role": "assistant", "content": f"Message {i}"},
                "evidence_id": None,
            }
            for i in range(5)
        ]

        summary = build_trace_summary(events)

        assert "2 more messages" in summary

    def test_limits_findings_display(self) -> None:
        """Summary limits findings to first 5."""
        events = [
            {
                "timestamp": float(i),
                "phase": "finding",
                "payload": {
                    "title": f"Finding {i}",
                    "cwe_id": f"CWE-{i}",
                    "severity": "medium",
                    "file_path": "test.py",
                },
                "evidence_id": None,
            }
            for i in range(8)
        ]

        summary = build_trace_summary(events)

        assert "and 3 more findings" in summary


class TestBuildTraceDetail:
    """Test structured trace timeline generation."""

    def test_empty_events_returns_empty_list(self) -> None:
        """Empty events list returns empty list."""
        detail = build_trace_detail([])
        assert detail == []

    def test_returns_structured_entries(self) -> None:
        """Each entry has required type and timestamp fields."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_call",
                "payload": {"tool_name": "bash", "arguments": {}},
                "evidence_id": "1",
            },
            {
                "timestamp": 2.0,
                "phase": "message",
                "payload": {"role": "user", "content": "test"},
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert len(detail) == 2
        assert detail[0]["type"] == "tool_call"
        assert detail[0]["timestamp"] == 1.0
        assert detail[1]["type"] == "message"
        assert detail[1]["timestamp"] == 2.0

    def test_tool_call_entry_structure(self) -> None:
        """Tool call entries include tool_name and arguments."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_call",
                "payload": {
                    "tool_name": "grep",
                    "arguments": {"pattern": "test"},
                },
                "evidence_id": "e1",
            },
        ]

        detail = build_trace_detail(events)

        assert detail[0]["type"] == "tool_call"
        assert detail[0]["tool_name"] == "grep"
        assert detail[0]["arguments"] == {"pattern": "test"}
        assert detail[0]["evidence_id"] == "e1"

    def test_tool_result_entry_structure(self) -> None:
        """Tool result entries include tool_name and summary."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_result",
                "payload": {
                    "tool_name": "grep",
                    "result_summary": "Found 3 matches",
                },
                "evidence_id": "e1",
            },
        ]

        detail = build_trace_detail(events)

        assert detail[0]["type"] == "tool_result"
        assert detail[0]["tool_name"] == "grep"
        assert detail[0]["result_summary"] == "Found 3 matches"

    def test_truncates_long_tool_result(self) -> None:
        """Long tool results are truncated to 500 chars."""
        long_summary = "x" * 1000
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_result",
                "payload": {
                    "tool_name": "grep",
                    "result_summary": long_summary,
                },
                "evidence_id": "e1",
            },
        ]

        detail = build_trace_detail(events)

        assert len(detail[0]["result_summary"]) == 500

    def test_message_entry_structure(self) -> None:
        """Message entries include role and content."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "message",
                "payload": {"role": "assistant", "content": "Found issue"},
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert detail[0]["type"] == "message"
        assert detail[0]["role"] == "assistant"
        assert detail[0]["content"] == "Found issue"

    def test_truncates_long_message_content(self) -> None:
        """Long message content is truncated to 500 chars."""
        long_content = "x" * 1000
        events = [
            {
                "timestamp": 1.0,
                "phase": "message",
                "payload": {"role": "assistant", "content": long_content},
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert len(detail[0]["content"]) == 500

    def test_finding_entry_structure(self) -> None:
        """Finding entries include all relevant fields."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "finding",
                "payload": {
                    "title": "Code injection",
                    "cwe_id": "CWE-95",
                    "file_path": "src/app.py",
                    "severity": "high",
                },
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert detail[0]["type"] == "finding"
        assert detail[0]["title"] == "Code injection"
        assert detail[0]["cwe_id"] == "CWE-95"
        assert detail[0]["file_path"] == "src/app.py"
        assert detail[0]["severity"] == "high"

    def test_error_entry_structure(self) -> None:
        """Error entries include error type and message."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "error",
                "payload": {"type": "RuntimeError", "message": "Tool failed"},
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert detail[0]["type"] == "error"
        assert detail[0]["error_type"] == "RuntimeError"
        assert detail[0]["error_message"] == "Tool failed"

    def test_done_entry_structure(self) -> None:
        """Done entries include status."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "done",
                "payload": {"status": "completed"},
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert detail[0]["type"] == "done"
        assert detail[0]["status"] == "completed"

    def test_all_event_types_in_sequence(self) -> None:
        """Handles all event types in a realistic sequence."""
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_call",
                "payload": {"tool_name": "grep", "arguments": {}},
                "evidence_id": "e1",
            },
            {
                "timestamp": 2.0,
                "phase": "tool_result",
                "payload": {"tool_name": "grep", "result_summary": "3 matches"},
                "evidence_id": "e1",
            },
            {
                "timestamp": 3.0,
                "phase": "message",
                "payload": {"role": "assistant", "content": "Analysis"},
                "evidence_id": None,
            },
            {
                "timestamp": 4.0,
                "phase": "finding",
                "payload": {
                    "title": "Issue",
                    "cwe_id": "CWE-79",
                    "file_path": "web.py",
                    "severity": "high",
                },
                "evidence_id": None,
            },
            {
                "timestamp": 5.0,
                "phase": "done",
                "payload": {"status": "completed"},
                "evidence_id": None,
            },
        ]

        detail = build_trace_detail(events)

        assert len(detail) == 5
        assert [e["type"] for e in detail] == [
            "tool_call",
            "tool_result",
            "message",
            "finding",
            "done",
        ]


class TestLocateTraceFiles:
    """Test trace file discovery and CWE mapping."""

    def test_empty_dir_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty or missing traces dir returns empty dict."""
        result = locate_trace_files(tmp_path)
        assert result == {}

    def test_finds_trace_files(self, tmp_path: Path) -> None:
        """Finds trace files and maps CWE IDs to them."""
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()

        trace_file = traces_dir / "test-1234-abcd.investigation.jsonl"
        events = [
            {
                "timestamp": 1.0,
                "phase": "finding",
                "payload": {"cwe_id": "CWE-95", "title": "Injection"},
                "evidence_id": None,
            },
            {
                "timestamp": 2.0,
                "phase": "finding",
                "payload": {"cwe_id": "CWE-79", "title": "XSS"},
                "evidence_id": None,
            },
        ]
        with open(trace_file, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        result = locate_trace_files(tmp_path)

        assert "CWE-95" in result
        assert "CWE-79" in result
        assert result["CWE-95"] == trace_file
        assert result["CWE-79"] == trace_file

    def test_maps_each_cwe_once(self, tmp_path: Path) -> None:
        """Each CWE is mapped to first trace file containing it."""
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()

        trace_file_1 = traces_dir / "test1-1234-abcd.investigation.jsonl"
        trace_file_2 = traces_dir / "test2-5678-efgh.investigation.jsonl"

        with open(trace_file_1, "w", encoding="utf-8") as f:
            event = {
                "timestamp": 1.0,
                "phase": "finding",
                "payload": {"cwe_id": "CWE-95"},
                "evidence_id": None,
            }
            f.write(json.dumps(event) + "\n")

        with open(trace_file_2, "w", encoding="utf-8") as f:
            event = {
                "timestamp": 2.0,
                "phase": "finding",
                "payload": {"cwe_id": "CWE-95"},
                "evidence_id": None,
            }
            f.write(json.dumps(event) + "\n")

        result = locate_trace_files(tmp_path)

        assert result["CWE-95"] == trace_file_1

    def test_skips_malformed_trace_files(self, tmp_path: Path) -> None:
        """Skips malformed trace files without crashing."""
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()

        bad_file = traces_dir / "bad.investigation.jsonl"
        bad_file.write_text("not valid json\n")

        good_file = traces_dir / "good-1234-abcd.investigation.jsonl"
        event = {
            "timestamp": 1.0,
            "phase": "finding",
            "payload": {"cwe_id": "CWE-79"},
            "evidence_id": None,
        }
        with open(good_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        result = locate_trace_files(tmp_path)

        assert "CWE-79" in result
        assert result["CWE-79"] == good_file

    def test_ignores_non_finding_events(self, tmp_path: Path) -> None:
        """Only processes finding phase events."""
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()

        trace_file = traces_dir / "test-1234-abcd.investigation.jsonl"
        events = [
            {
                "timestamp": 1.0,
                "phase": "tool_call",
                "payload": {"tool_name": "grep", "cwe_id": "CWE-95"},
                "evidence_id": None,
            },
            {
                "timestamp": 2.0,
                "phase": "finding",
                "payload": {"cwe_id": "CWE-79"},
                "evidence_id": None,
            },
        ]
        with open(trace_file, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        result = locate_trace_files(tmp_path)

        assert "CWE-95" not in result
        assert "CWE-79" in result

    def test_skips_findings_without_cwe_id(self, tmp_path: Path) -> None:
        """Skips findings that don't have cwe_id."""
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()

        trace_file = traces_dir / "test-1234-abcd.investigation.jsonl"
        event = {
            "timestamp": 1.0,
            "phase": "finding",
            "payload": {"title": "Issue"},
            "evidence_id": None,
        }
        with open(trace_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        result = locate_trace_files(tmp_path)

        assert result == {}
