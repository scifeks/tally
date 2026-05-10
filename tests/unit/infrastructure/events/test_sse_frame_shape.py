import json
from datetime import UTC, datetime

from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import BusEvent


def _ev(event_type: str, payload: dict) -> BusEvent:
    return BusEvent(
        event_id="evt1",
        job_id="j1",
        stream="scan",
        event_type=event_type,
        payload=payload,
        ts=datetime.now(tz=UTC),
    )


def test_frame_has_correct_shape():
    frame = format_sse_frame(_ev("ScanLogEvent", {"msg": "hello"}))
    parts = frame.split("\n")
    assert parts[0] == "event: ScanLogEvent"
    assert parts[1].startswith("data: ")
    assert parts[2] == ""
    assert parts[3] == ""
    assert frame.endswith("\n\n")


def test_event_type_passes_through():
    for event_type in (
        "ScanLogEvent",
        "TriageLogEvent",
        "ReportLogEvent",
        "ChatStreamEvent",
    ):
        frame = format_sse_frame(_ev(event_type, {}))
        assert frame.startswith(f"event: {event_type}\n")


def test_data_is_valid_json():
    frame = format_sse_frame(_ev("log", {"key": "value"}))
    data_line = frame.split("\n")[1]
    parsed = json.loads(data_line[len("data: ") :])
    assert parsed == {"key": "value"}
