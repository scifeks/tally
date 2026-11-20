"""Typed JSONL event schema for the host-container SDK relay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class EventParseError(ValueError):
    """Raised when a JSONL line cannot be decoded as a known event."""


@dataclass(frozen=True)
class AssistantTextEvent:
    text: str


@dataclass(frozen=True)
class ToolUseEvent:
    name: str
    tool_input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultEvent:
    text: str
    is_error: bool


@dataclass(frozen=True)
class ErrorEvent:
    status_code: int | None
    subtype: str
    message: str


@dataclass(frozen=True)
class EndEvent:
    pass


Event = AssistantTextEvent | ToolUseEvent | ResultEvent | ErrorEvent | EndEvent


def parse_event(line: str) -> Event:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise EventParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise EventParseError("event payload must be a JSON object")
    kind = obj.get("type")
    if kind == "assistant_text":
        return AssistantTextEvent(text=str(obj.get("text", "")))
    if kind == "tool_use":
        raw_input = obj.get("tool_input")
        if raw_input is None:
            tool_input: dict[str, Any] = {}
        elif isinstance(raw_input, dict):
            tool_input = dict(raw_input)
        else:
            raise EventParseError(
                f"tool_input must be a JSON object, got {type(raw_input).__name__}"
            )
        return ToolUseEvent(name=str(obj.get("name", "")), tool_input=tool_input)
    if kind == "result":
        return ResultEvent(
            text=str(obj.get("text", "")),
            is_error=bool(obj.get("is_error", False)),
        )
    if kind == "error":
        return ErrorEvent(
            status_code=obj.get("status_code"),
            subtype=str(obj.get("subtype", "")),
            message=str(obj.get("message", "")),
        )
    if kind == "end":
        return EndEvent()
    raise EventParseError(f"unknown event type: {kind!r}")


def serialize_event(event: Event) -> str:
    if isinstance(event, AssistantTextEvent):
        return json.dumps({"type": "assistant_text", "text": event.text})
    if isinstance(event, ToolUseEvent):
        return json.dumps(
            {
                "type": "tool_use",
                "name": event.name,
                "tool_input": event.tool_input,
            }
        )
    if isinstance(event, ResultEvent):
        return json.dumps(
            {"type": "result", "text": event.text, "is_error": event.is_error}
        )
    if isinstance(event, ErrorEvent):
        return json.dumps(
            {
                "type": "error",
                "status_code": event.status_code,
                "subtype": event.subtype,
                "message": event.message,
            }
        )
    if isinstance(event, EndEvent):
        return json.dumps({"type": "end"})
    raise TypeError(f"unknown event: {type(event)!r}")
