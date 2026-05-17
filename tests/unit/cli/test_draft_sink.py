"""Unit tests for CLI draft event sink."""

from __future__ import annotations

from application.cli.draft_sink import CliDraftEventSink
from domain.pipeline.report_events import DraftCompleted, DraftFailed, DraftStarted


class TestCliDraftEventSinkDraftStarted:
    def test_prints_generating_message_to_stdout(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftStarted(
            report_id=1,
            project_id=1,
            section="executive_summary",
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert "Generating executive_summary..." in captured.out

    def test_includes_section_name_in_message(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftStarted(
            report_id=1,
            project_id=1,
            section="methodology",
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert "Generating methodology..." in captured.out


class TestCliDraftEventSinkDraftCompleted:
    def test_prints_saved_message_to_stdout(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftCompleted(
            report_id=1,
            project_id=1,
            section="findings",
            output_path="/tmp/draft.md",
            file_size_bytes=1024,
            word_count=500,
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert "Draft saved: /tmp/draft.md" in captured.out

    def test_includes_output_path_in_message(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftCompleted(
            report_id=1,
            project_id=1,
            section="executive_summary",
            output_path="/home/user/reports/draft_2025_05_10.md",
            file_size_bytes=2048,
            word_count=1000,
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert "/home/user/reports/draft_2025_05_10.md" in captured.out


class TestCliDraftEventSinkDraftFailed:
    def test_prints_error_message_to_stderr(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftFailed(
            report_id=1,
            project_id=1,
            section="executive_summary",
            error="Connection timeout",
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert "Error: Connection timeout" in captured.err

    def test_does_not_print_to_stdout_on_failure(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftFailed(
            report_id=1,
            project_id=1,
            section="findings",
            error="Failed to process findings",
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert captured.out == ""
        assert "Failed to process findings" in captured.err

    def test_includes_error_message_in_output(self, capsys) -> None:
        sink = CliDraftEventSink()
        event = DraftFailed(
            report_id=1,
            project_id=1,
            section="methodology",
            error="LLM provider unavailable",
        )

        sink.emit(event)
        captured = capsys.readouterr()

        assert "LLM provider unavailable" in captured.err


class TestCliDraftEventSinkUnknownEvent:
    def test_ignores_unknown_event_type(self, capsys) -> None:
        sink = CliDraftEventSink()

        # Create a mock event that is not a recognized type
        class UnknownEvent:
            pass

        unknown = UnknownEvent()

        # Unknown event types are silently ignored
        sink.emit(unknown)  # type: ignore
        captured = capsys.readouterr()

        assert captured.out == ""
        assert captured.err == ""
