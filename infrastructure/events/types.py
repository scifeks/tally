from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, NewType

SubscriberId = NewType("SubscriberId", str)


@dataclass(frozen=True)
class BusEvent:
    event_id: str
    job_id: str
    stream: Literal["scan", "triage", "report", "report_draft", "chat", "finding"]
    event_type: str
    payload: Mapping[str, Any]
    ts: datetime


class _EOSType:
    def __repr__(self) -> str:
        return "EOS"


EOS = _EOSType()
