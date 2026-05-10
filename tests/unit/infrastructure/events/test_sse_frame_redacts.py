import json
from datetime import UTC, datetime

from infrastructure.events.sse import format_sse_frame
from infrastructure.events.types import BusEvent


def _ev(payload: dict) -> BusEvent:
    return BusEvent(
        event_id="evt1",
        job_id="j1",
        stream="scan",
        event_type="log",
        payload=payload,
        ts=datetime.now(tz=UTC),
    )


def _data(frame: str) -> dict:
    data_line = frame.split("\n")[1]
    return json.loads(data_line[len("data: ") :])


def test_api_key_redacted():
    frame = format_sse_frame(_ev({"api_key": "sekrit", "other": "ok"}))
    data = _data(frame)
    assert data["api_key"] == "***REDACTED***"
    assert data["other"] == "ok"


def test_nested_token_redacted():
    frame = format_sse_frame(_ev({"config": {"token": "mysecret", "safe": "v"}}))
    data = _data(frame)
    assert data["config"]["token"] == "***REDACTED***"
    assert data["config"]["safe"] == "v"


def test_authorization_header_redacted():
    frame = format_sse_frame(
        _ev({"headers": {"Authorization": "Bearer tok", "X-Safe": "v"}})
    )
    data = _data(frame)
    assert data["headers"]["Authorization"] == "***REDACTED***"
    assert data["headers"]["X-Safe"] == "v"


def test_url_token_param_redacted():
    frame = format_sse_frame(
        _ev({"url": "https://example.com/api?token=secret123&safe=ok"})
    )
    data = _data(frame)
    assert "secret123" not in data["url"]
    assert "***REDACTED***" in data["url"]


def test_already_redacted_is_idempotent():
    frame = format_sse_frame(_ev({"api_key": "***REDACTED***"}))
    data = _data(frame)
    assert data["api_key"] == "***REDACTED***"
