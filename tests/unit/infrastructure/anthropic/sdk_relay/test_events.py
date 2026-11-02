"""Protocol-level tests for the host-container JSONL event schema."""

from __future__ import annotations

import json

import pytest

from infrastructure.anthropic.sdk_relay.events import (
    AssistantTextEvent,
    EndEvent,
    ErrorEvent,
    EventParseError,
    ResultEvent,
    ToolUseEvent,
    parse_event,
    serialize_event,
)


def test_assistant_text_roundtrip() -> None:
    e = AssistantTextEvent(text="hello")
    assert parse_event(serialize_event(e)) == e


def test_tool_use_roundtrip() -> None:
    e = ToolUseEvent(name="Read", tool_input={"file_path": "/x"})
    assert parse_event(serialize_event(e)) == e


def test_result_roundtrip() -> None:
    e = ResultEvent(text='{"finding_id":1}', is_error=False)
    assert parse_event(serialize_event(e)) == e


def test_error_with_status_code_roundtrip() -> None:
    e = ErrorEvent(status_code=429, subtype="rate_limit", message="slow down")
    assert parse_event(serialize_event(e)) == e


def test_error_without_status_code_roundtrip() -> None:
    e = ErrorEvent(status_code=None, subtype="timeout", message="deadline")
    assert parse_event(serialize_event(e)) == e


def test_end_roundtrip() -> None:
    assert parse_event(serialize_event(EndEvent())) == EndEvent()


def test_malformed_json_raises() -> None:
    with pytest.raises(EventParseError):
        parse_event("not json")


def test_missing_type_raises() -> None:
    with pytest.raises(EventParseError):
        parse_event(json.dumps({"text": "hi"}))


def test_unknown_type_raises() -> None:
    with pytest.raises(EventParseError):
        parse_event(json.dumps({"type": "mystery"}))


def test_serialize_includes_type_field() -> None:
    line = serialize_event(AssistantTextEvent(text="x"))
    assert json.loads(line)["type"] == "assistant_text"


@pytest.mark.parametrize("bad_input", ["abc", 5, True, [1, 2]])
def test_tool_use_non_dict_tool_input_raises(bad_input: object) -> None:
    payload = json.dumps({"type": "tool_use", "name": "Read", "tool_input": bad_input})
    with pytest.raises(EventParseError):
        parse_event(payload)


def test_tool_use_null_tool_input_defaults_to_empty() -> None:
    payload = json.dumps({"type": "tool_use", "name": "Read", "tool_input": None})
    event = parse_event(payload)
    assert isinstance(event, ToolUseEvent)
    assert event.tool_input == {}
